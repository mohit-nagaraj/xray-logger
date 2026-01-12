"""Public type definitions and constants for X-Ray SDK.

This module exposes the key constants and types that users may need
when working with payload summarization and externalization.
"""

# Re-export constants from internal module for public API
from ._internal.step import (
    LARGE_LIST_THRESHOLD,
    LARGE_STRING_THRESHOLD,
    PREVIEW_SIZE,
    STRING_PREVIEW_SIZE,
)

# Re-export shared types for convenience
from shared.types import RunStatus, StepStatus, StepType

__all__ = [
    # Payload externalization thresholds
    "LARGE_LIST_THRESHOLD",
    "LARGE_STRING_THRESHOLD",
    "PREVIEW_SIZE",
    "STRING_PREVIEW_SIZE",
    # Status/type enums
    "RunStatus",
    "StepStatus",
    "StepType",
]
