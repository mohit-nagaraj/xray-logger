"""Pydantic schemas for API request/response validation.

This module defines the schemas for the /ingest endpoint that receives
events from the SDK transport layer. Uses discriminated unions for
automatic event type routing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Event Schemas (SDK → API)
# =============================================================================


class RunStartEvent(BaseModel):
    """Event sent when a run begins.

    Created by SDK's Run.__init__ and sent via transport.
    """

    model_config = ConfigDict(populate_by_name=True)

    event_type: Literal["run_start"]
    id: UUID
    pipeline_name: str
    status: Literal["running"]
    started_at: datetime
    input_summary: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    request_id: str | None = None
    user_id: str | None = None
    environment: str | None = None
    payloads: dict[str, Any] | None = Field(default=None, alias="_payloads")


class RunEndEvent(BaseModel):
    """Event sent when a run completes or errors.

    Created by SDK's Run.end() and sent via transport.
    """

    model_config = ConfigDict(populate_by_name=True)

    event_type: Literal["run_end"]
    id: UUID
    status: Literal["success", "error"]
    ended_at: datetime
    output_summary: dict[str, Any] | None = None
    error_message: str | None = None
    payloads: dict[str, Any] | None = Field(default=None, alias="_payloads")


class StepStartEvent(BaseModel):
    """Event sent when a step begins.

    Created by SDK's Step.__init__ and sent via transport.
    """

    model_config = ConfigDict(populate_by_name=True)

    event_type: Literal["step_start"]
    id: UUID
    run_id: UUID
    step_name: str
    step_type: str
    index: int
    started_at: datetime
    input_summary: dict[str, Any] | None = None
    input_count: int | None = None
    metadata: dict[str, Any] | None = None
    payloads: dict[str, Any] | None = Field(default=None, alias="_payloads")


class StepEndEvent(BaseModel):
    """Event sent when a step completes or errors.

    Created by SDK's Step.end() and sent via transport.
    """

    model_config = ConfigDict(populate_by_name=True)

    event_type: Literal["step_end"]
    id: UUID
    run_id: UUID
    status: Literal["success", "error"]
    ended_at: datetime
    duration_ms: int | None = None
    output_summary: dict[str, Any] | None = None
    output_count: int | None = None
    reasoning: dict[str, Any] | None = None
    error_message: str | None = None
    payloads: dict[str, Any] | None = Field(default=None, alias="_payloads")


# Discriminated union for automatic event type routing
IngestEvent = Annotated[
    RunStartEvent | RunEndEvent | StepStartEvent | StepEndEvent,
    Field(discriminator="event_type"),
]


# =============================================================================
# Response Schemas
# =============================================================================


class EventResult(BaseModel):
    """Result for a single event in the batch."""

    id: UUID
    event_type: str
    success: bool
    error: str | None = None


class IngestResponse(BaseModel):
    """Response for the /ingest endpoint.

    Always returns HTTP 200 with success/failure counts.
    This supports fail-open semantics - SDK shouldn't retry
    partial failures.
    """

    processed: int
    succeeded: int
    failed: int
    results: list[EventResult]
