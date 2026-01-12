"""Pytest fixtures for E2E integration tests.

Provides fixtures for:
- In-memory SQLite database for test isolation
- FastAPI test app with dependency overrides
- Uvicorn server running in background thread
- X-Ray SDK client configured for test server
- Async HTTP client for API queries
"""

import socket
import threading
import time
from typing import AsyncGenerator, Generator

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api._internal.database import get_session
from api.models import Base
from api.routes import router
from sdk import XRayConfig, init_xray, shutdown_xray


def _enable_sqlite_fk(dbapi_conn, connection_record):
    """Enable foreign key support in SQLite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _find_free_port() -> int:
    """Find a free port to use for the test server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="function")
async def test_engine():
    """Create an in-memory SQLite engine for testing.

    Each test gets a fresh database with all tables created.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    event.listen(engine.sync_engine, "connect", _enable_sqlite_fk)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest.fixture(scope="function")
async def test_session_factory(test_engine):
    """Create a session factory for the test database."""
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return factory


@pytest.fixture(scope="function")
def test_app(test_engine, test_session_factory) -> FastAPI:
    """Create test FastAPI app with overridden database dependency."""
    app = FastAPI()
    app.include_router(router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    return app


@pytest.fixture(scope="function")
def api_server(test_app) -> Generator[str, None, None]:
    """Start uvicorn server in background thread, return base URL.

    Uses a dynamically allocated port to avoid conflicts.
    Waits for server to be ready before yielding.
    """
    port = _find_free_port()

    config = uvicorn.Config(
        app=test_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to be ready
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):  # 10 second timeout
        try:
            response = httpx.get(f"{base_url}/xray/runs", timeout=0.1)
            if response.status_code == 200:
                break
        except (httpx.ConnectError, httpx.ReadTimeout):
            time.sleep(0.1)
    else:
        raise RuntimeError("Test server failed to start")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5.0)


@pytest.fixture(scope="function")
def xray_client(api_server):
    """Initialize X-Ray SDK pointing to test server.

    Uses fast flush interval for quicker test execution.
    """
    config = XRayConfig(
        base_url=api_server,
        buffer_size=100,
        flush_interval=0.3,  # Fast flush for tests
    )
    client = init_xray(config)
    yield client
    shutdown_xray(timeout=3.0)


@pytest.fixture(scope="function")
async def api_client(api_server) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for querying API endpoints."""
    async with httpx.AsyncClient(base_url=api_server, timeout=10.0) as client:
        yield client
