"""Shared type definitions for X-Ray SDK and API.

These enums inherit from both `str` and `Enum` to ensure JSON serializability.
This allows `json.dumps(StepType.filter)` to work directly without custom encoders.
"""

from enum import Enum


class StepType(str, Enum):
    """Type of processing step in a pipeline.

    Used to categorize steps for filtering and analysis:
    - filter: Reduces candidates based on criteria
    - rank: Orders/scores candidates
    - llm: LLM API call
    - retrieval: Fetches data from external sources
    - transform: Transforms data format/structure
    - other: Uncategorized steps
    """

    filter = "filter"
    rank = "rank"
    llm = "llm"
    retrieval = "retrieval"
    transform = "transform"
    other = "other"


class RunStatus(str, Enum):
    """Status of a pipeline run.

    Lifecycle: running -> success | error
    """

    running = "running"
    success = "success"
    error = "error"


class StepStatus(str, Enum):
    """Status of a single step within a run.

    Lifecycle: running -> success | error
    """

    running = "running"
    success = "success"
    error = "error"


class DetailLevel(str, Enum):
    """Payload capture detail level.

    Controls how much data is captured for inputs/outputs:
    - summary: Counts and small samples only (default, recommended)
    - full: Complete payload up to size threshold
    """

    summary = "summary"
    full = "full"
