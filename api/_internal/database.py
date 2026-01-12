"""Database engine and session configuration.

This module provides async database connectivity using SQLAlchemy 2.0
with the asyncpg driver for PostgreSQL.

Usage:
    from api.database import init_db, get_session, close_db
    from api.config import load_config

    # At application startup
    config = load_config()
    await init_db(config)

    # In FastAPI routes (dependency injection)
    async def my_route(session: AsyncSession = Depends(get_session)):
        ...

    # At application shutdown
    await close_db()
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import APIConfig
from ..models import Base

# Global engine and session factory (initialized by init_db)
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(config: APIConfig) -> None:
    """Initialize database engine and create tables.

    Creates the async engine with the configured database URL and
    sets up the session factory. Also creates all tables defined
    in the ORM models if they don't exist.

    Args:
        config: API configuration containing database_url and debug flag.

    Raises:
        RuntimeError: If called when database is already initialized.
        Exception: Re-raises any exception from engine creation or table creation,
                   after cleaning up globals to leave module in consistent state.
    """
    global _engine, _session_factory

    if _engine is not None:
        raise RuntimeError("Database already initialized. Call close_db() first.")

    engine = create_async_engine(
        config.database_url,
        echo=config.debug,
        pool_pre_ping=True,  # Verify connections before use
    )

    try:
        # Create tables if they don't exist
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Only set globals after successful table creation
        _engine = engine
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,  # Keep objects usable after commit
        )
    except Exception:
        # Clean up engine on failure to leave module in consistent state
        await engine.dispose()
        raise


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session.

    This is designed to be used as a FastAPI dependency. The session
    is automatically closed when the request completes.

    Yields:
        AsyncSession: Database session for the request.

    Raises:
        RuntimeError: If database is not initialized.

    Example:
        @app.get("/runs/{run_id}")
        async def get_run(
            run_id: UUID,
            session: AsyncSession = Depends(get_session)
        ):
            return await store.get_run(session, run_id)
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with _session_factory() as session:
        yield session


async def close_db() -> None:
    """Close database connections and dispose of the engine.

    Should be called at application shutdown to cleanly release
    all database connections.
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def _get_engine() -> AsyncEngine | None:
    """Get the database engine (internal/testing use).

    Returns:
        The async engine, or None if not initialized.
    """
    return _engine


def is_initialized() -> bool:
    """Check if the database is initialized.

    Returns:
        True if init_db() has been called and close_db() has not.
    """
    return _engine is not None
