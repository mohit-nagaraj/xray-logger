"""X-Ray SDK for instrumenting pipelines."""

from .client import (
    XRayClient,
    current_run,
    current_step,
    get_client,
    init_xray,
    shutdown_xray,
)
from .config import XRayConfig, load_config
from .decorators import (
    attach_candidates,
    attach_reasoning,
    instrument_class,
    step,
)
from .middleware import XRayMiddleware
from .run import Run
from .step import (
    LARGE_LIST_THRESHOLD,
    LARGE_STRING_THRESHOLD,
    PREVIEW_SIZE,
    STRING_PREVIEW_SIZE,
    PayloadCollector,
    Step,
    infer_count,
    summarize_payload,
)
from .transport import Transport

__all__ = [
    # Client and context management
    "XRayClient",
    "init_xray",
    "get_client",
    "current_run",
    "current_step",
    "shutdown_xray",
    # Configuration
    "XRayConfig",
    "load_config",
    # Decorators
    "step",
    "instrument_class",
    # Helpers
    "attach_reasoning",
    "attach_candidates",
    # Core classes
    "Transport",
    "Run",
    "Step",
    "PayloadCollector",
    "XRayMiddleware",
    # Utilities
    "infer_count",
    "summarize_payload",
    # Constants
    "LARGE_LIST_THRESHOLD",
    "LARGE_STRING_THRESHOLD",
    "PREVIEW_SIZE",
    "STRING_PREVIEW_SIZE",
]
