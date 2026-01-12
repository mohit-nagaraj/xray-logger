"""X-Ray API backend.

This package provides the FastAPI backend for storing and querying
pipeline observability data captured by the X-Ray SDK.

Usage:
    uvicorn api.main:app --reload
"""

# Configuration
from .config import APIConfig, load_config

# Database (from internal)
from ._internal.database import close_db, get_session, init_db, is_initialized

# Application
from .main import app, create_app

# ORM Models (public for querying)
from .models import Base, Payload, Run, Step

# API Routes
from .routes import router

# Pydantic Schemas (public API contract)
from .schemas import (
    EventResult,
    IngestEvent,
    IngestResponse,
    RunEndEvent,
    RunStartEvent,
    StepEndEvent,
    StepStartEvent,
)

__all__ = [
    # Configuration
    "APIConfig",
    "load_config",
    # Database
    "init_db",
    "get_session",
    "close_db",
    "is_initialized",
    # Models
    "Base",
    "Payload",
    "Run",
    "Step",
    # Application
    "app",
    "create_app",
    "router",
    # Schemas
    "EventResult",
    "IngestEvent",
    "IngestResponse",
    "RunStartEvent",
    "RunEndEvent",
    "StepStartEvent",
    "StepEndEvent",
]
