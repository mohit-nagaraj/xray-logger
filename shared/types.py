"""Shared type definitions for X-Ray SDK and API."""

from enum import Enum


class StepType(str, Enum):
    """Type of processing step in a pipeline."""

    filter = "filter"
    rank = "rank"
    llm = "llm"
    retrieval = "retrieval"
    transform = "transform"
    other = "other"


class RunStatus(str, Enum):
    """Status of a pipeline run."""

    running = "running"
    success = "success"
    error = "error"


class StepStatus(str, Enum):
    """Status of a single step within a run."""

    running = "running"
    success = "success"
    error = "error"


class DetailLevel(str, Enum):
    """Payload capture detail level."""

    summary = "summary"
    full = "full"
