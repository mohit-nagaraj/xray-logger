"""Tests for API routes (/ingest endpoint)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api import store
from api.database import get_session
from api.models import Base


def _enable_sqlite_fk(dbapi_conn, connection_record):
    """Enable foreign key support in SQLite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
async def engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    # Enable foreign key enforcement in SQLite
    event.listen(engine.sync_engine, "connect", _enable_sqlite_fk)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncSession:
    """Create a test database session."""
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
def client(engine, session):
    """Create test client with overridden database dependency.

    We create a minimal app without lifespan since we manage
    the database manually in the test fixtures.
    """
    from fastapi import FastAPI
    from api.routes import router

    # Create app without lifespan (no init_db call)
    app = FastAPI()
    app.include_router(router)

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as c:
        yield c


class TestIngestEmpty:
    """Tests for empty batch handling."""

    def test_ingest_empty_batch(self, client):
        """Ingest with empty array returns success with zero counts."""
        response = client.post("/ingest", json=[])
        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == 0
        assert data["succeeded"] == 0
        assert data["failed"] == 0
        assert data["results"] == []


class TestIngestRunStart:
    """Tests for run_start event ingestion."""

    def test_ingest_run_start_minimal(self, client):
        """Ingest run_start with only required fields."""
        event = {
            "event_type": "run_start",
            "id": str(uuid4()),
            "pipeline_name": "test_pipeline",
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        response = client.post("/ingest", json=[event])
        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == 1
        assert data["succeeded"] == 1
        assert data["failed"] == 0

    def test_ingest_run_start_full(self, client):
        """Ingest run_start with all fields."""
        event = {
            "event_type": "run_start",
            "id": str(uuid4()),
            "pipeline_name": "recommendation_pipeline",
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "input_summary": {"query": "test", "_count": 10},
            "metadata": {"custom_field": "value"},
            "request_id": "req-123",
            "user_id": "user-456",
            "environment": "production",
        }
        response = client.post("/ingest", json=[event])
        assert response.status_code == 200
        assert response.json()["succeeded"] == 1

    def test_ingest_run_start_with_payloads(self, client):
        """Ingest run_start with externalized payloads."""
        event = {
            "event_type": "run_start",
            "id": str(uuid4()),
            "pipeline_name": "test",
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "_payloads": {
                "p-001": list(range(100)),
                "p-002": "x" * 2000,
            },
        }
        response = client.post("/ingest", json=[event])
        assert response.status_code == 200
        assert response.json()["succeeded"] == 1


class TestIngestRunEnd:
    """Tests for run_end event ingestion."""

    def test_ingest_run_end_success(self, client):
        """Ingest run_end after run_start."""
        run_id = str(uuid4())

        # First create the run
        start_event = {
            "event_type": "run_start",
            "id": run_id,
            "pipeline_name": "test",
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        client.post("/ingest", json=[start_event])

        # Then end it
        end_event = {
            "event_type": "run_end",
            "id": run_id,
            "status": "success",
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "output_summary": {"result": "done"},
        }
        response = client.post("/ingest", json=[end_event])
        assert response.status_code == 200
        assert response.json()["succeeded"] == 1

    def test_ingest_run_end_error(self, client):
        """Ingest run_end with error status."""
        run_id = str(uuid4())

        start_event = {
            "event_type": "run_start",
            "id": run_id,
            "pipeline_name": "test",
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        client.post("/ingest", json=[start_event])

        end_event = {
            "event_type": "run_end",
            "id": run_id,
            "status": "error",
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "error_message": "Something went wrong",
        }
        response = client.post("/ingest", json=[end_event])
        assert response.status_code == 200
        assert response.json()["succeeded"] == 1

    def test_ingest_run_end_not_found(self, client):
        """Ingest run_end for non-existent run returns failure."""
        event = {
            "event_type": "run_end",
            "id": str(uuid4()),
            "status": "success",
            "ended_at": datetime.now(timezone.utc).isoformat(),
        }
        response = client.post("/ingest", json=[event])
        assert response.status_code == 200
        data = response.json()
        assert data["succeeded"] == 0
        assert data["failed"] == 1
        assert "not found" in data["results"][0]["error"]


class TestIngestStepStart:
    """Tests for step_start event ingestion."""

    def test_ingest_step_start(self, client):
        """Ingest step_start after run_start."""
        run_id = str(uuid4())
        step_id = str(uuid4())

        # Create run first
        start_event = {
            "event_type": "run_start",
            "id": run_id,
            "pipeline_name": "test",
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        client.post("/ingest", json=[start_event])

        # Create step
        step_event = {
            "event_type": "step_start",
            "id": step_id,
            "run_id": run_id,
            "step_name": "filter_step",
            "step_type": "filter",
            "index": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "input_summary": {"items": 100},
            "input_count": 100,
        }
        response = client.post("/ingest", json=[step_event])
        assert response.status_code == 200
        assert response.json()["succeeded"] == 1

    def test_ingest_step_start_orphan(self, client):
        """Ingest step_start without parent run fails due to FK constraint."""
        event = {
            "event_type": "step_start",
            "id": str(uuid4()),
            "run_id": str(uuid4()),  # Non-existent run
            "step_name": "orphan_step",
            "step_type": "filter",
            "index": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        response = client.post("/ingest", json=[event])
        assert response.status_code == 200
        data = response.json()
        assert data["failed"] == 1


class TestIngestStepEnd:
    """Tests for step_end event ingestion."""

    def test_ingest_step_end_success(self, client):
        """Ingest step_end after step_start."""
        run_id = str(uuid4())
        step_id = str(uuid4())

        # Create run and step
        events = [
            {
                "event_type": "run_start",
                "id": run_id,
                "pipeline_name": "test",
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "event_type": "step_start",
                "id": step_id,
                "run_id": run_id,
                "step_name": "filter",
                "step_type": "filter",
                "index": 0,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        client.post("/ingest", json=events)

        # End step
        end_event = {
            "event_type": "step_end",
            "id": step_id,
            "run_id": run_id,
            "status": "success",
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": 150,
            "output_summary": {"items": 50},
            "output_count": 50,
        }
        response = client.post("/ingest", json=[end_event])
        assert response.status_code == 200
        assert response.json()["succeeded"] == 1

    def test_ingest_step_end_with_reasoning(self, client):
        """Ingest step_end with reasoning attached."""
        run_id = str(uuid4())
        step_id = str(uuid4())

        events = [
            {
                "event_type": "run_start",
                "id": run_id,
                "pipeline_name": "test",
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "event_type": "step_start",
                "id": step_id,
                "run_id": run_id,
                "step_name": "rank",
                "step_type": "rank",
                "index": 0,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        client.post("/ingest", json=events)

        end_event = {
            "event_type": "step_end",
            "id": step_id,
            "run_id": run_id,
            "status": "success",
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "reasoning": {
                "algorithm": "bm25",
                "top_scores": [0.95, 0.87, 0.72],
            },
        }
        response = client.post("/ingest", json=[end_event])
        assert response.status_code == 200
        assert response.json()["succeeded"] == 1

    def test_ingest_step_end_not_found(self, client):
        """Ingest step_end for non-existent step returns failure."""
        event = {
            "event_type": "step_end",
            "id": str(uuid4()),
            "run_id": str(uuid4()),
            "status": "success",
            "ended_at": datetime.now(timezone.utc).isoformat(),
        }
        response = client.post("/ingest", json=[event])
        assert response.status_code == 200
        data = response.json()
        assert data["failed"] == 1
        assert "not found" in data["results"][0]["error"]


class TestIngestFullLifecycle:
    """Tests for complete run lifecycle ingestion."""

    def test_ingest_full_lifecycle(self, client):
        """Ingest complete run with multiple steps in single batch."""
        run_id = str(uuid4())
        step1_id = str(uuid4())
        step2_id = str(uuid4())

        events = [
            {
                "event_type": "run_start",
                "id": run_id,
                "pipeline_name": "recommendation_pipeline",
                "status": "running",
                "started_at": "2024-01-15T10:30:00Z",
                "input_summary": {"user_id": "u123", "query": "shoes"},
            },
            {
                "event_type": "step_start",
                "id": step1_id,
                "run_id": run_id,
                "step_name": "retrieve_candidates",
                "step_type": "retrieval",
                "index": 0,
                "started_at": "2024-01-15T10:30:01Z",
            },
            {
                "event_type": "step_end",
                "id": step1_id,
                "run_id": run_id,
                "status": "success",
                "ended_at": "2024-01-15T10:30:02Z",
                "duration_ms": 1000,
                "output_count": 100,
            },
            {
                "event_type": "step_start",
                "id": step2_id,
                "run_id": run_id,
                "step_name": "filter_by_price",
                "step_type": "filter",
                "index": 1,
                "started_at": "2024-01-15T10:30:02Z",
                "input_count": 100,
            },
            {
                "event_type": "step_end",
                "id": step2_id,
                "run_id": run_id,
                "status": "success",
                "ended_at": "2024-01-15T10:30:03Z",
                "duration_ms": 500,
                "output_count": 25,
            },
            {
                "event_type": "run_end",
                "id": run_id,
                "status": "success",
                "ended_at": "2024-01-15T10:30:03Z",
                "output_summary": {"recommendations": 25},
            },
        ]

        response = client.post("/ingest", json=events)
        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == 6
        assert data["succeeded"] == 6
        assert data["failed"] == 0

    def test_ingest_partial_failure(self, client):
        """Ingest batch with some valid and some invalid events."""
        run_id = str(uuid4())

        events = [
            # Valid: run_start
            {
                "event_type": "run_start",
                "id": run_id,
                "pipeline_name": "test",
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
            # Invalid: step_end for non-existent step
            {
                "event_type": "step_end",
                "id": str(uuid4()),
                "run_id": run_id,
                "status": "success",
                "ended_at": datetime.now(timezone.utc).isoformat(),
            },
            # Valid: run_end
            {
                "event_type": "run_end",
                "id": run_id,
                "status": "success",
                "ended_at": datetime.now(timezone.utc).isoformat(),
            },
        ]

        response = client.post("/ingest", json=events)
        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == 3
        assert data["succeeded"] == 2
        assert data["failed"] == 1

        # Check individual results
        assert data["results"][0]["success"] is True
        assert data["results"][1]["success"] is False
        assert data["results"][2]["success"] is True


class TestIngestValidation:
    """Tests for request validation."""

    def test_ingest_invalid_event_type(self, client):
        """Invalid event_type returns 422 validation error."""
        event = {
            "event_type": "invalid_type",
            "id": str(uuid4()),
        }
        response = client.post("/ingest", json=[event])
        assert response.status_code == 422

    def test_ingest_invalid_uuid(self, client):
        """Invalid UUID format returns 422 validation error."""
        event = {
            "event_type": "run_start",
            "id": "not-a-uuid",
            "pipeline_name": "test",
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        response = client.post("/ingest", json=[event])
        assert response.status_code == 422

    def test_ingest_missing_required_field(self, client):
        """Missing required field returns 422 validation error."""
        event = {
            "event_type": "run_start",
            "id": str(uuid4()),
            # Missing: pipeline_name, status, started_at
        }
        response = client.post("/ingest", json=[event])
        assert response.status_code == 422

    def test_ingest_invalid_status(self, client):
        """Invalid status value returns 422 validation error."""
        event = {
            "event_type": "run_start",
            "id": str(uuid4()),
            "pipeline_name": "test",
            "status": "invalid_status",  # Should be "running"
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        response = client.post("/ingest", json=[event])
        assert response.status_code == 422


class TestIngestPayloads:
    """Tests for payload externalization handling."""

    @pytest.mark.asyncio
    async def test_payloads_stored_correctly(self, client, session):
        """Verify payloads are stored in the database."""
        run_id = uuid4()

        event = {
            "event_type": "run_start",
            "id": str(run_id),
            "pipeline_name": "test",
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "_payloads": {
                "p-001": list(range(50)),
                "p-002": {"nested": "data"},
            },
        }
        response = client.post("/ingest", json=[event])
        assert response.status_code == 200
        assert response.json()["succeeded"] == 1

        # Verify payloads were stored
        payloads = await store.get_payloads(session, run_id=run_id)
        assert len(payloads) == 2

        ref_ids = {p.ref_id for p in payloads}
        assert ref_ids == {"p-001", "p-002"}

        # All should be input phase for run_start
        assert all(p.phase == "input" for p in payloads)

    @pytest.mark.asyncio
    async def test_step_payloads_linked_correctly(self, client, session):
        """Verify step payloads are linked to the correct step."""
        run_id = uuid4()
        step_id = uuid4()

        events = [
            {
                "event_type": "run_start",
                "id": str(run_id),
                "pipeline_name": "test",
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "event_type": "step_start",
                "id": str(step_id),
                "run_id": str(run_id),
                "step_name": "process",
                "step_type": "transform",
                "index": 0,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "_payloads": {"p-input": [1, 2, 3]},
            },
            {
                "event_type": "step_end",
                "id": str(step_id),
                "run_id": str(run_id),
                "status": "success",
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "_payloads": {"p-output": [4, 5, 6]},
            },
        ]
        response = client.post("/ingest", json=events)
        assert response.status_code == 200
        assert response.json()["succeeded"] == 3

        # Verify step payloads
        payloads = await store.get_payloads(session, run_id=run_id, step_id=step_id)
        assert len(payloads) == 2

        input_payload = next(p for p in payloads if p.phase == "input")
        output_payload = next(p for p in payloads if p.phase == "output")

        assert input_payload.ref_id == "p-input"
        assert input_payload.step_id == step_id
        assert output_payload.ref_id == "p-output"
        assert output_payload.step_id == step_id
