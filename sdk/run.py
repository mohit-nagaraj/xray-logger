"""Run class for X-Ray SDK - represents a complete pipeline execution."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from shared.types import RunStatus, StepType

from .step import PayloadCollector, Step, summarize_payload
from .transport import Transport


class Run:
    """Represents a complete pipeline execution.

    Lifecycle:
        1. Created via XRayClient.start_run() or directly
        2. Create steps via run.start_step()
        3. Call run.end() when pipeline completes

    Supports context manager protocol for automatic ending.
    """

    def __init__(
        self,
        transport: Transport,
        pipeline_name: str,
        input_data: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a new Run.

        Args:
            transport: Transport for sending events
            pipeline_name: Name of the pipeline (e.g., "recommendation_pipeline")
            input_data: Optional pipeline input to summarize
            metadata: Optional metadata (request_id, user_id, environment, etc.)
        """
        self._id = str(uuid.uuid4())
        self._transport = transport
        self._pipeline_name = pipeline_name
        self._metadata = metadata or {}

        # Timing
        self._started_at = datetime.now(timezone.utc)
        self._ended_at: datetime | None = None

        # Input/output - use collector for large data externalization
        # Note: use 'is not None' to handle falsy but valid inputs like [], 0, "", False
        self._input_collector = PayloadCollector()
        self._input_summary = (
            summarize_payload(input_data, collector=self._input_collector)
            if input_data is not None
            else None
        )
        self._output_summary: dict[str, Any] | None = None
        self._output_payloads: dict[str, Any] | None = None

        # Status
        self._status: RunStatus = RunStatus.running
        self._error_message: str | None = None

        # Step tracking
        self._step_index = 0
        self._steps: list[Step] = []

        # Send run start event
        self._send_start_event()

    @property
    def id(self) -> str:
        """Run unique identifier."""
        return self._id

    @property
    def pipeline_name(self) -> str:
        """Pipeline name."""
        return self._pipeline_name

    @property
    def status(self) -> RunStatus:
        """Current run status."""
        return self._status

    @property
    def metadata(self) -> dict[str, Any]:
        """Run metadata."""
        return self._metadata

    def start_step(
        self,
        name: str,
        step_type: StepType | str = StepType.other,
        input_data: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> Step:
        """Create and start a new Step within this Run.

        Args:
            name: Step name
            step_type: Type of step
            input_data: Input data to this step
            metadata: Optional step metadata

        Returns:
            New Step instance (already started)

        Raises:
            RuntimeError: If the run has already ended
        """
        if self._ended_at is not None:
            raise RuntimeError(
                f"Cannot start step '{name}' - run '{self._id}' has already ended"
            )

        step = Step(
            run=self,
            transport=self._transport,
            name=name,
            step_type=step_type,
            input_data=input_data,
            index=self._step_index,
            metadata=metadata,
        )
        self._steps.append(step)
        self._step_index += 1
        return step

    def _finalize_run(
        self,
        status: RunStatus,
        output: Any = None,
        error: BaseException | str | None = None,
    ) -> None:
        """Internal method to finalize the run.

        Args:
            status: Final status
            output: Optional output data
            error: Optional error (BaseException or string)
        """
        if self._ended_at is not None:
            return  # Already ended, idempotent

        self._ended_at = datetime.now(timezone.utc)
        self._status = status

        if error is not None:
            # Use BaseException to handle KeyboardInterrupt, SystemExit, etc.
            if isinstance(error, BaseException):
                self._error_message = f"{type(error).__name__}: {error!s}"
            else:
                self._error_message = str(error)

        if output is not None:
            output_collector = PayloadCollector()
            self._output_summary = summarize_payload(output, collector=output_collector)
            self._output_payloads = output_collector.get_payloads()

        self._send_end_event()

    def end(
        self,
        output: Any = None,
        status: RunStatus | str = RunStatus.success,
    ) -> None:
        """End the run.

        Args:
            output: Final pipeline output
            status: Final status (success or error)
        """
        final_status = RunStatus(status) if isinstance(status, str) else status
        self._finalize_run(status=final_status, output=output)

    def end_with_error(self, error: BaseException | str, output: Any = None) -> None:
        """End the run with an error.

        Args:
            error: Exception/BaseException or error message
            output: Optional partial output
        """
        self._finalize_run(status=RunStatus.error, output=output, error=error)

    def __enter__(self) -> Run:
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        """Context manager exit - auto-end the run."""
        if exc_val is not None:
            self.end_with_error(exc_val)
        else:
            self.end()
        return False  # Don't suppress exceptions

    def _send_start_event(self) -> None:
        """Send run start event to transport."""
        event: dict[str, Any] = {
            "event_type": "run_start",
            "id": self._id,
            "pipeline_name": self._pipeline_name,
            "status": self._status.value,
            "started_at": self._started_at.isoformat(),
            "input_summary": self._input_summary,
            "_payloads": self._input_collector.get_payloads(),
        }

        # Add metadata fields (flatten common ones for indexing)
        if self._metadata:
            event["metadata"] = self._metadata
            # Extract common fields to top level for indexing
            for key in ("request_id", "user_id", "environment"):
                if key in self._metadata:
                    event[key] = self._metadata[key]

        self._transport.send(event)

    def _send_end_event(self) -> None:
        """Send run end event to transport."""
        event: dict[str, Any] = {
            "event_type": "run_end",
            "id": self._id,
            "status": self._status.value,
            "ended_at": self._ended_at.isoformat() if self._ended_at else None,
            "output_summary": self._output_summary,
            "error_message": self._error_message,
            "_payloads": self._output_payloads,
        }
        self._transport.send(event)
