"""FastAPI application factory for the X-Ray API.

This module provides the application factory and lifespan handler
for database initialization and cleanup.

Usage:
    # Development
    uvicorn api.main:app --reload

    # Production
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import load_config
from .database import close_db, init_db
from .routes import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup and shutdown.

    Startup:
        - Load configuration
        - Initialize database connection and create tables

    Shutdown:
        - Close database connections

    Args:
        app: The FastAPI application instance
    """
    # Startup
    config = load_config()
    await init_db(config)

    # Log authentication status
    if config.api_key:
        logger.info("API authentication: ENABLED (XRAY_API_KEY is set)")
    else:
        logger.info("API authentication: DISABLED (open access)")

    yield

    # Shutdown
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application with routes mounted.
    """
    app = FastAPI(
        title="X-Ray API",
        description="Decision-reasoning observability API for multi-step pipelines",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(router)

    return app


# Application instance for uvicorn
app = create_app()
