"""FastAPI route handlers for the X-Ray API.

This module provides the /ingest endpoint that receives batched events
from the SDK transport layer. Events are processed sequentially to
maintain temporal dependencies (run before step, start before end).
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from . import store
from .auth import verify_api_key
from .database import get_session
from .models import Step
from .schemas import (
    EventResult,
    IngestEvent,
    IngestResponse,
    RunDetailResponse,
    RunEndEvent,
    RunListResponse,
    RunStartEvent,
    RunSummaryResponse,
    StepEndEvent,
    StepListResponse,
    StepResponse,
    StepStartEvent,
)

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse, dependencies=[Depends(verify_api_key)])
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


# =============================================================================
# Query Endpoints
# =============================================================================


def compute_removed_ratio(
    input_count: int | None, output_count: int | None
) -> float | None:
    """Compute removed_ratio = (input - output) / input.

    Returns None for edge cases:
    - input_count is None (unknown input)
    - input_count is 0 (division by zero)
    - output_count is None (unknown output)
    """
    if input_count is None or output_count is None:
        return None
    if input_count == 0:
        return None
    return (input_count - output_count) / input_count


def _step_to_response(step: Step) -> StepResponse:
    """Convert Step ORM model to StepResponse with computed removed_ratio."""
    return StepResponse(
        id=step.id,
        run_id=step.run_id,
        step_name=step.step_name,
        step_type=step.step_type,
        index=step.index,
        started_at=step.started_at,
        ended_at=step.ended_at,
        duration_ms=step.duration_ms,
        input_summary=step.input_summary,
        output_summary=step.output_summary,
        input_count=step.input_count,
        output_count=step.output_count,
        removed_ratio=compute_removed_ratio(step.input_count, step.output_count),
        reasoning=step.reasoning,
        metadata=step.metadata_,
        status=step.status,
        error_message=step.error_message,
    )


@router.get("/xray/runs/{run_id}", response_model=RunDetailResponse, dependencies=[Depends(verify_api_key)])
async def get_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> RunDetailResponse:
    """Get a single run by ID with all its steps.

    Steps are returned ordered by started_at ascending (execution order).

    Args:
        run_id: UUID of the run to fetch

    Returns:
        Run with all steps including computed removed_ratio for each step

    Raises:
        HTTPException 404: If run not found
    """
    run = await store.get_run(session, run_id, include_steps=True)

    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Sort steps by started_at (ascending) for execution order
    sorted_steps = sorted(run.steps, key=lambda s: (s.started_at, s.index))

    return RunDetailResponse(
        id=run.id,
        pipeline_name=run.pipeline_name,
        status=run.status,
        started_at=run.started_at,
        ended_at=run.ended_at,
        input_summary=run.input_summary,
        output_summary=run.output_summary,
        metadata=run.metadata_,
        request_id=run.request_id,
        user_id=run.user_id,
        environment=run.environment,
        error_message=run.error_message,
        steps=[_step_to_response(step) for step in sorted_steps],
    )


@router.get("/xray/runs", response_model=RunListResponse, dependencies=[Depends(verify_api_key)])
async def list_runs(
    session: AsyncSession = Depends(get_session),
    pipeline_name: str | None = Query(default=None, alias="pipeline"),
    status: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> RunListResponse:
    """List runs with optional filters and pagination.

    Runs are returned in descending order by started_at (most recent first).

    Args:
        pipeline: Filter by pipeline name
        status: Filter by status (running, success, error)
        user_id: Filter by user ID
        request_id: Filter by request ID
        environment: Filter by environment
        limit: Maximum number of results (1-1000, default 100)
        offset: Number of results to skip (default 0)

    Returns:
        Paginated list of runs (without steps)
    """
    # Note: Sequential queries required - AsyncSession is not safe for concurrent use
    total = await store.count_runs(
        session,
        pipeline_name=pipeline_name,
        status=status,
        user_id=user_id,
        request_id=request_id,
        environment=environment,
    )
    runs = await store.list_runs(
        session,
        pipeline_name=pipeline_name,
        status=status,
        user_id=user_id,
        request_id=request_id,
        environment=environment,
        limit=limit,
        offset=offset,
    )

    return RunListResponse(
        runs=[RunSummaryResponse.model_validate(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/xray/steps", response_model=StepListResponse, dependencies=[Depends(verify_api_key)])
async def list_steps(
    session: AsyncSession = Depends(get_session),
    run_id: UUID | None = Query(default=None),
    step_type: str | None = Query(default=None),
    step_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> StepListResponse:
    """List steps with optional filters and pagination.

    Steps are returned in descending order by started_at (most recent first).
    Each step includes the computed removed_ratio metric.

    Args:
        run_id: Filter by parent run ID
        step_type: Filter by step type (filter, rank, llm, etc.)
        step_name: Filter by step name
        status: Filter by status (running, success, error)
        limit: Maximum number of results (1-1000, default 100)
        offset: Number of results to skip (default 0)

    Returns:
        Paginated list of steps with computed removed_ratio
    """
    # Note: Sequential queries required - AsyncSession is not safe for concurrent use
    total = await store.count_steps(
        session,
        run_id=run_id,
        step_type=step_type,
        step_name=step_name,
        status=status,
    )
    steps = await store.list_steps(
        session,
        run_id=run_id,
        step_type=step_type,
        step_name=step_name,
        status=status,
        limit=limit,
        offset=offset,
    )

    return StepListResponse(
        steps=[_step_to_response(step) for step in steps],
        total=total,
        limit=limit,
        offset=offset,
    )
