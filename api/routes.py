"""FastAPI route handlers for the X-Ray API.

This module provides the /ingest endpoint that receives batched events
from the SDK transport layer. Events are processed sequentially to
maintain temporal dependencies (run before step, start before end).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from . import store
from .database import get_session
from .schemas import (
    EventResult,
    IngestEvent,
    IngestResponse,
    RunEndEvent,
    RunStartEvent,
    StepEndEvent,
    StepStartEvent,
)

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse)
async def ingest_events(
    events: list[IngestEvent],
    session: AsyncSession = Depends(get_session),
) -> IngestResponse:
    """Ingest a batch of events from the SDK.

    Processes events sequentially in the order received. Each event
    is handled independently - failures in one event don't affect others.

    Always returns HTTP 200 with success/failure counts in the body.
    This supports fail-open semantics - the SDK should not retry
    on partial failures.

    Args:
        events: List of events (run_start, run_end, step_start, step_end)
        session: Database session (injected)

    Returns:
        IngestResponse with processed/succeeded/failed counts and per-event results.
    """
    results: list[EventResult] = []

    for event in events:
        try:
            await _process_event(session, event)
            results.append(
                EventResult(
                    id=event.id,
                    event_type=event.event_type,
                    success=True,
                )
            )
        except Exception as e:
            logger.exception(
                "Error processing event %s of type %s", event.id, event.event_type
            )
            results.append(
                EventResult(
                    id=event.id,
                    event_type=event.event_type,
                    success=False,
                    error=str(e),
                )
            )

    succeeded = sum(1 for r in results if r.success)
    return IngestResponse(
        processed=len(events),
        succeeded=succeeded,
        failed=len(events) - succeeded,
        results=results,
    )


async def _process_event(session: AsyncSession, event: IngestEvent) -> None:
    """Process a single event, dispatching to the appropriate handler.

    Args:
        session: Database session
        event: The event to process (discriminated union)

    Raises:
        ValueError: If referenced run/step not found
        Exception: Database errors propagate up
    """
    match event.event_type:
        case "run_start":
            await _handle_run_start(session, event)
        case "run_end":
            await _handle_run_end(session, event)
        case "step_start":
            await _handle_step_start(session, event)
        case "step_end":
            await _handle_step_end(session, event)


async def _handle_run_start(session: AsyncSession, event: RunStartEvent) -> None:
    """Handle run_start event - creates a new Run record.

    Also stores any externalized payloads from the _payloads field.
    Payload failures are logged but don't fail the event (run is already saved).
    """
    await store.create_run(
        session,
        id=event.id,
        pipeline_name=event.pipeline_name,
        status=event.status,
        started_at=event.started_at,
        input_summary=event.input_summary,
        metadata=event.metadata,
        request_id=event.request_id,
        user_id=event.user_id,
        environment=event.environment,
    )

    # Store externalized payloads if present
    # Failures are logged but don't fail the event (run is already committed)
    if event.payloads:
        try:
            await store.create_payloads(
                session,
                run_id=event.id,
                step_id=None,  # Run-level payloads
                phase="input",
                payloads=event.payloads,
            )
        except Exception:
            logger.exception("Failed to store payloads for run %s", event.id)


async def _handle_run_end(session: AsyncSession, event: RunEndEvent) -> None:
    """Handle run_end event - updates existing Run with completion data.

    Raises:
        ValueError: If the run doesn't exist
    """
    result = await store.end_run(
        session,
        id=event.id,
        status=event.status,
        ended_at=event.ended_at,
        output_summary=event.output_summary,
        error_message=event.error_message,
    )

    if result is None:
        raise ValueError(f"Run {event.id} not found")

    # Store externalized payloads if present
    # Failures are logged but don't fail the event (run is already committed)
    if event.payloads:
        try:
            await store.create_payloads(
                session,
                run_id=event.id,
                step_id=None,  # Run-level payloads
                phase="output",
                payloads=event.payloads,
            )
        except Exception:
            logger.exception("Failed to store payloads for run %s", event.id)


async def _handle_step_start(session: AsyncSession, event: StepStartEvent) -> None:
    """Handle step_start event - creates a new Step record.

    Also stores any externalized payloads from the _payloads field.
    Payload failures are logged but don't fail the event (step is already saved).
    """
    await store.create_step(
        session,
        id=event.id,
        run_id=event.run_id,
        step_name=event.step_name,
        step_type=event.step_type,
        index=event.index,
        started_at=event.started_at,
        status="running",
        input_summary=event.input_summary,
        input_count=event.input_count,
        metadata=event.metadata,
    )

    # Store externalized payloads if present
    # Failures are logged but don't fail the event (step is already committed)
    if event.payloads:
        try:
            await store.create_payloads(
                session,
                run_id=event.run_id,
                step_id=event.id,
                phase="input",
                payloads=event.payloads,
            )
        except Exception:
            logger.exception("Failed to store payloads for step %s", event.id)


async def _handle_step_end(session: AsyncSession, event: StepEndEvent) -> None:
    """Handle step_end event - updates existing Step with completion data.

    Raises:
        ValueError: If the step doesn't exist
    """
    result = await store.end_step(
        session,
        id=event.id,
        status=event.status,
        ended_at=event.ended_at,
        duration_ms=event.duration_ms,
        output_summary=event.output_summary,
        output_count=event.output_count,
        reasoning=event.reasoning,
        error_message=event.error_message,
    )

    if result is None:
        raise ValueError(f"Step {event.id} not found")

    # Store externalized payloads if present
    # Use result.run_id (verified from DB) instead of event.run_id for data consistency
    # Failures are logged but don't fail the event (step is already committed)
    if event.payloads:
        try:
            await store.create_payloads(
                session,
                run_id=result.run_id,  # Use verified run_id from database
                step_id=event.id,
                phase="output",
                payloads=event.payloads,
            )
        except Exception:
            logger.exception("Failed to store payloads for step %s", event.id)
