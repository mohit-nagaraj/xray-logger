"""X-Ray SDK for instrumenting pipelines.

This package provides tools for capturing decision-reasoning observability
in multi-step pipelines. It records why decisions were made, not just
what functions ran.

Quick Start:
    from sdk import init_xray, step, XRayConfig

    # Initialize at startup
    init_xray(XRayConfig(base_url="http://localhost:8000"))

    # Decorate pipeline functions
    @step(step_type="filter")
    def filter_candidates(candidates):
        return [c for c in candidates if c["score"] > 0.5]
"""

# Public client API
from .client import (
    XRayClient,
    current_run,
    current_step,
    get_client,
    init_xray,
    shutdown_xray,
)

# Configuration
from .config import XRayConfig, load_config

# Public decorators and helpers
from .decorators import (
    attach_candidates,
    attach_reasoning,
    instrument_class,
    step,
)

# Middleware
from .middleware import XRayMiddleware

# Internal classes exposed for type hints and advanced usage
from ._internal import (
    LARGE_LIST_THRESHOLD,
    LARGE_STRING_THRESHOLD,
    PREVIEW_SIZE,
    STRING_PREVIEW_SIZE,
    PayloadCollector,
    Run,
    Step,
    Transport,
    infer_count,
    summarize_payload,
)

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
