"""Step class and payload summarization helpers for X-Ray SDK."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from shared.types import StepStatus, StepType

if TYPE_CHECKING:
    from .run import Run
    from .transport import Transport

# Summarization constants
MAX_STRING_LENGTH = 1024  # Truncate long strings (not IDs)
MAX_DICT_KEYS = 50  # Max keys to extract from dicts
MAX_PAYLOAD_DEPTH = 5  # Max recursion depth for nested structures

# Common ID field names to check
ID_FIELDS = ("id", "_id", "candidate_id", "item_id", "product_id", "doc_id")


def infer_count(obj: Any) -> int | None:
    """Infer item count from an object.

    Args:
        obj: Any Python object

    Returns:
        Integer count for list-like objects, None otherwise
    """
    if obj is None:
        return None

    # Check for list, tuple, set, frozenset
    if isinstance(obj, (list, tuple, set, frozenset)):
        return len(obj)

    # Check for dict with explicit "items" or "results" key
    if isinstance(obj, dict):
        for key in ("items", "results", "data", "records", "candidates"):
            if key in obj and isinstance(obj[key], (list, tuple)):
                return len(obj[key])

    # Check for __len__ on iterables (but not strings/dicts)
    if hasattr(obj, "__len__") and not isinstance(obj, (str, bytes, dict)):
        try:
            return len(obj)
        except (TypeError, AttributeError):
            pass

    return None


def is_candidate_list(obj: Any) -> bool:
    """Check if object is a list of candidate-like dicts.

    A candidate list is a list of dicts where each dict has an ID field.

    Args:
        obj: Any Python object

    Returns:
        True if obj appears to be a list of candidates
    """
    if not isinstance(obj, (list, tuple)):
        return False

    if len(obj) == 0:
        return False

    # Check first few items to determine if this is a candidate list
    sample_size = min(3, len(obj))
    for item in obj[:sample_size]:
        if not isinstance(item, dict):
            return False
        # Check if any ID field exists
        if not any(field in item for field in ID_FIELDS):
            return False

    return True


def extract_candidate(item: dict[str, Any]) -> dict[str, Any]:
    """Extract id, score, and reason from a candidate dict.

    Args:
        item: A candidate dict with at least an ID field

    Returns:
        Dict with id, score (if present), and reason (if present)
    """
    result: dict[str, Any] = {}

    # Extract ID (try common field names)
    for field in ID_FIELDS:
        if field in item:
            result["id"] = item[field]
            break

    # Extract score if present
    for field in ("score", "rank", "relevance", "confidence", "weight"):
        if field in item:
            result["score"] = item[field]
            break

    # Extract reason if present
    for field in ("reason", "explanation", "rationale", "why", "filter_reason"):
        if field in item:
            result["reason"] = item[field]
            break

    # If no reason found, set to None
    if "reason" not in result:
        result["reason"] = None

    return result


def _truncate_string(s: str, max_length: int = MAX_STRING_LENGTH) -> str:
    """Truncate a string if it exceeds max length."""
    if len(s) <= max_length:
        return s
    return s[:max_length] + "..."


def summarize_payload(obj: Any, depth: int = 0) -> dict[str, Any]:
    """Summarize a payload for storage.

    For candidate lists: Extract ALL id + score + reason (no sampling).
    For other data: Store keys + truncated values.

    Args:
        obj: Object to summarize
        depth: Current recursion depth

    Returns:
        JSON-serializable dict with summary
    """
    # Base case: max depth reached
    if depth >= MAX_PAYLOAD_DEPTH:
        return {"_type": type(obj).__name__, "_truncated": True}

    # Handle None
    if obj is None:
        return {"_type": "null", "_value": None}

    # Handle bool (must check before int since bool is subclass of int)
    if isinstance(obj, bool):
        return {"_type": "bool", "_value": obj}

    # Handle numbers
    if isinstance(obj, (int, float)):
        return {"_type": type(obj).__name__, "_value": obj}

    # Handle strings
    if isinstance(obj, str):
        truncated = len(obj) > MAX_STRING_LENGTH
        return {
            "_type": "str",
            "_length": len(obj),
            "_value": _truncate_string(obj),
            "_truncated": truncated,
        }

    # Handle bytes
    if isinstance(obj, bytes):
        return {"_type": "bytes", "_length": len(obj)}

    # Handle candidate lists specially - extract ALL ids
    if is_candidate_list(obj):
        candidates = [extract_candidate(item) for item in obj]
        return {
            "_type": "candidates",
            "_count": len(obj),
            "_candidates": candidates,
        }

    # Handle other lists/tuples/sets
    if isinstance(obj, (list, tuple, set, frozenset)):
        count = len(obj)
        result: dict[str, Any] = {
            "_type": type(obj).__name__,
            "_count": count,
        }
        # For non-candidate lists, just store type info of first item
        if count > 0:
            first_item = list(obj)[0]
            result["_item_type"] = type(first_item).__name__
        return result

    # Handle dicts
    if isinstance(obj, dict):
        keys = list(obj.keys())[:MAX_DICT_KEYS]
        result = {
            "_type": "dict",
            "_key_count": len(obj),
            "_keys": [str(k) for k in keys],
        }
        if len(obj) > MAX_DICT_KEYS:
            result["_keys_truncated"] = True

        # Include scalar values directly
        values: dict[str, Any] = {}
        for k in keys:
            v = obj[k]
            if v is None:
                values[str(k)] = None
            elif isinstance(v, bool):
                values[str(k)] = v
            elif isinstance(v, (int, float)):
                values[str(k)] = v
            elif isinstance(v, str):
                values[str(k)] = _truncate_string(v)
            else:
                # For complex types, just note the type
                values[str(k)] = {"_type": type(v).__name__}
        result["_values"] = values
        return result

    # Handle other objects
    type_name = type(obj).__name__
    result = {"_type": type_name}

    # Try to get "id" attribute for identification
    if hasattr(obj, "id"):
        try:
            result["_id"] = str(getattr(obj, "id"))
        except Exception:
            pass

    return result


class Step:
    """Represents a single decision step within a Run.

    Lifecycle:
        1. Created via Run.start_step()
        2. Execute business logic
        3. Call step.end(output) or step.end_with_error(error)

    The Step automatically captures timing, input/output counts,
    and sends events to the transport layer.
    """

    def __init__(
        self,
        run: Run,
        transport: Transport,
        name: str,
        step_type: StepType | str,
        input_data: Any,
        index: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a new Step.

        Args:
            run: Parent Run instance
            transport: Transport for sending events
            name: Step name (e.g., "filter_by_price")
            step_type: Type of step (filter, rank, llm, etc.)
            input_data: Input to this step
            index: Step index within run (0-based)
            metadata: Optional metadata dict
        """
        self._id = str(uuid.uuid4())
        self._run = run
        self._transport = transport
        self._name = name
        self._step_type = StepType(step_type) if isinstance(step_type, str) else step_type
        self._index = index
        self._metadata = metadata or {}
        self._reasoning: dict[str, Any] = {}

        # Timing
        self._started_at = datetime.now(timezone.utc)
        self._start_time_ns = time.perf_counter_ns()
        self._ended_at: datetime | None = None
        self._duration_ms: int | None = None

        # Input processing
        self._input_summary = summarize_payload(input_data)
        self._input_count = infer_count(input_data)

        # Output (set on end)
        self._output_summary: dict[str, Any] | None = None
        self._output_count: int | None = None
        self._status: StepStatus = StepStatus.running
        self._error_message: str | None = None

        # Send step start event
        self._send_start_event()

    @property
    def id(self) -> str:
        """Step unique identifier."""
        return self._id

    @property
    def run_id(self) -> str:
        """Parent run ID."""
        return self._run.id

    @property
    def name(self) -> str:
        """Step name."""
        return self._name

    @property
    def step_type(self) -> StepType:
        """Step type."""
        return self._step_type

    @property
    def status(self) -> StepStatus:
        """Current step status."""
        return self._status

    def attach_reasoning(self, reasoning: dict[str, Any] | str) -> None:
        """Attach reasoning information to this step.

        Args:
            reasoning: Reasoning dict or string explanation
        """
        if isinstance(reasoning, str):
            self._reasoning["explanation"] = reasoning
        else:
            self._reasoning.update(reasoning)

    def end(
        self,
        output: Any,
        status: StepStatus | str = StepStatus.success,
    ) -> None:
        """End the step with output.

        Args:
            output: Step output data
            status: Final status (success or error)
        """
        if self._ended_at is not None:
            return  # Already ended, idempotent

        self._ended_at = datetime.now(timezone.utc)
        end_time_ns = time.perf_counter_ns()
        self._duration_ms = (end_time_ns - self._start_time_ns) // 1_000_000

        self._status = StepStatus(status) if isinstance(status, str) else status
        self._output_summary = summarize_payload(output)
        self._output_count = infer_count(output)

        self._send_end_event()

    def end_with_error(self, error: Exception | str) -> None:
        """End the step with an error.

        Args:
            error: Exception or error message
        """
        if self._ended_at is not None:
            return  # Already ended

        self._ended_at = datetime.now(timezone.utc)
        end_time_ns = time.perf_counter_ns()
        self._duration_ms = (end_time_ns - self._start_time_ns) // 1_000_000

        self._status = StepStatus.error
        if isinstance(error, Exception):
            self._error_message = f"{type(error).__name__}: {error!s}"
        else:
            self._error_message = str(error)

        self._send_end_event()

    def _send_start_event(self) -> None:
        """Send step start event to transport."""
        event = {
            "event_type": "step_start",
            "id": self._id,
            "run_id": self._run.id,
            "step_name": self._name,
            "step_type": self._step_type.value,
            "index": self._index,
            "started_at": self._started_at.isoformat(),
            "input_summary": self._input_summary,
            "input_count": self._input_count,
            "metadata": self._metadata if self._metadata else None,
        }
        self._transport.send(event)

    def _send_end_event(self) -> None:
        """Send step end event to transport."""
        event = {
            "event_type": "step_end",
            "id": self._id,
            "run_id": self._run.id,
            "status": self._status.value,
            "ended_at": self._ended_at.isoformat() if self._ended_at else None,
            "duration_ms": self._duration_ms,
            "output_summary": self._output_summary,
            "output_count": self._output_count,
            "reasoning": self._reasoning if self._reasoning else None,
            "error_message": self._error_message,
        }
        self._transport.send(event)
