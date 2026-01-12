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


# =============================================================================
# Query Response Schemas (API → Client)
# =============================================================================


class StepResponse(BaseModel):
    """Response schema for a Step in query results.

    Includes the computed removed_ratio field that is calculated dynamically
    from input_count and output_count.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    run_id: UUID
    step_name: str
    step_type: str
    index: int
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    input_count: int | None = None
    output_count: int | None = None
    removed_ratio: float | None = None  # Computed: (input - output) / input
    reasoning: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="metadata_")
    status: str | None = None
    error_message: str | None = None


class RunSummaryResponse(BaseModel):
    """Response schema for Run in list results (without steps)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    pipeline_name: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="metadata_")
    request_id: str | None = None
    user_id: str | None = None
    environment: str | None = None
    error_message: str | None = None


class RunDetailResponse(RunSummaryResponse):
    """Response schema for Run with steps (single run fetch)."""

    steps: list[StepResponse] = []


class RunListResponse(BaseModel):
    """Paginated response for listing runs."""

    runs: list[RunSummaryResponse]
    total: int
    limit: int
    offset: int


class StepListResponse(BaseModel):
    """Paginated response for listing steps."""

    steps: list[StepResponse]
    total: int
    limit: int
    offset: int
