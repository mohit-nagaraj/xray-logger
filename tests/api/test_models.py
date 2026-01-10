"""Tests for API database models."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from api.models import Base, Payload, Run, Step


def _enable_sqlite_fk(dbapi_conn, connection_record):
    """Enable foreign key support in SQLite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
async def engine():
    """Create an in-memory SQLite engine for testing."""
    # Use SQLite for fast, isolated tests (actual app uses PostgreSQL)
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


class TestRunModel:
    """Tests for Run model."""

    async def test_run_creates_with_required_fields(self, session: AsyncSession) -> None:
        """Run model creates with required fields."""
        run = Run(
            id=uuid4(),
            pipeline_name="test_pipeline",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

        assert run.id is not None
        assert run.pipeline_name == "test_pipeline"
        assert run.status == "running"
        assert run.started_at is not None

    async def test_run_creates_with_all_fields(self, session: AsyncSession) -> None:
        """Run model creates with all fields."""
        run_id = uuid4()
        started = datetime.now(timezone.utc)

        run = Run(
            id=run_id,
            pipeline_name="recommendation_pipeline",
            status="success",
            started_at=started,
            ended_at=started,
            input_summary={"query": "test", "_count": 10},
            output_summary={"results": 5},
            metadata_={"request_id": "req-123", "user_id": "user-456"},
            request_id="req-123",
            user_id="user-456",
            environment="production",
            error_message=None,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

        assert run.id == run_id
        assert run.pipeline_name == "recommendation_pipeline"
        assert run.input_summary == {"query": "test", "_count": 10}
        assert run.metadata_ == {"request_id": "req-123", "user_id": "user-456"}
        assert run.request_id == "req-123"
        assert run.user_id == "user-456"
        assert run.environment == "production"

    async def test_run_default_values(self, session: AsyncSession) -> None:
        """Run model has expected default values."""
        run = Run(
            id=uuid4(),
            pipeline_name="test",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

        # status has a default
        assert run.status == "running"
        # Optional fields default to None
        assert run.ended_at is None
        assert run.input_summary is None
        assert run.output_summary is None
        assert run.metadata_ is None
        assert run.request_id is None
        assert run.error_message is None

    async def test_run_stores_json_fields(self, session: AsyncSession) -> None:
        """Run model properly stores JSON fields."""
        complex_metadata = {
            "nested": {"key": "value"},
            "array": [1, 2, 3],
            "number": 42,
            "boolean": True,
            "null": None,
        }

        run = Run(
            id=uuid4(),
            pipeline_name="test",
            started_at=datetime.now(timezone.utc),
            metadata_=complex_metadata,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

        assert run.metadata_ == complex_metadata
        assert run.metadata_["nested"]["key"] == "value"
        assert run.metadata_["array"] == [1, 2, 3]


class TestStepModel:
    """Tests for Step model."""

    async def test_step_creates_with_required_fields(self, session: AsyncSession) -> None:
        """Step model creates with required fields."""
        # First create a run for the foreign key
        run = Run(
            id=uuid4(),
            pipeline_name="test_pipeline",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

        step = Step(
            id=uuid4(),
            run_id=run.id,
            step_name="filter_step",
            step_type="filter",
            index=0,
            started_at=datetime.now(timezone.utc),
        )
        session.add(step)
        await session.commit()
        await session.refresh(step)

        assert step.id is not None
        assert step.run_id == run.id
        assert step.step_name == "filter_step"
        assert step.step_type == "filter"
        assert step.index == 0

    async def test_step_creates_with_all_fields(self, session: AsyncSession) -> None:
        """Step model creates with all fields."""
        run = Run(
            id=uuid4(),
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

        step_id = uuid4()
        started = datetime.now(timezone.utc)

        step = Step(
            id=step_id,
            run_id=run.id,
            step_name="rank_candidates",
            step_type="rank",
            index=1,
            started_at=started,
            ended_at=started,
            duration_ms=150,
            input_summary={"candidates": 100},
            output_summary={"ranked": 10},
            input_count=100,
            output_count=10,
            reasoning={"algorithm": "bm25", "threshold": 0.5},
            metadata_={"source": "cache"},
            status="success",
            error_message=None,
        )
        session.add(step)
        await session.commit()
        await session.refresh(step)

        assert step.id == step_id
        assert step.duration_ms == 150
        assert step.input_count == 100
        assert step.output_count == 10
        assert step.reasoning == {"algorithm": "bm25", "threshold": 0.5}
        assert step.status == "success"


class TestRunStepRelationship:
    """Tests for Run-Step relationship."""

    async def test_run_has_steps_relationship(self, session: AsyncSession) -> None:
        """Run model has steps relationship."""
        run_id = uuid4()
        run = Run(
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

        # Add steps
        for i in range(3):
            step = Step(
                id=uuid4(),
                run_id=run.id,
                step_name=f"step_{i}",
                step_type="other",
                index=i,
                started_at=datetime.now(timezone.utc),
            )
            session.add(step)

        await session.commit()

        # Re-query with steps loaded (SQLite doesn't refresh relationships)
        stmt = select(Run).where(Run.id == run_id).options(selectinload(Run.steps))
        result = await session.execute(stmt)
        loaded_run = result.scalar_one()

        assert len(loaded_run.steps) == 3

    async def test_steps_ordered_by_index(self, session: AsyncSession) -> None:
        """Run.steps are ordered by index."""
        run_id = uuid4()
        run = Run(
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

        # Add steps in reverse order
        for i in [2, 0, 1]:
            step = Step(
                id=uuid4(),
                run_id=run.id,
                step_name=f"step_{i}",
                step_type="other",
                index=i,
                started_at=datetime.now(timezone.utc),
            )
            session.add(step)

        await session.commit()

        # Re-query with steps loaded (SQLite doesn't refresh relationships)
        stmt = select(Run).where(Run.id == run_id).options(selectinload(Run.steps))
        result = await session.execute(stmt)
        loaded_run = result.scalar_one()

        # Should be ordered by index
        assert [s.index for s in loaded_run.steps] == [0, 1, 2]

    async def test_step_has_run_relationship(self, session: AsyncSession) -> None:
        """Step model has run relationship."""
        run = Run(
            id=uuid4(),
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

        step = Step(
            id=uuid4(),
            run_id=run.id,
            step_name="test_step",
            step_type="other",
            index=0,
            started_at=datetime.now(timezone.utc),
        )
        session.add(step)
        await session.commit()
        await session.refresh(step)

        assert step.run.id == run.id
        assert step.run.pipeline_name == "test"

    async def test_cascade_delete(self, session: AsyncSession) -> None:
        """Deleting a run cascades to its steps."""
        run = Run(
            id=uuid4(),
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

        step = Step(
            id=uuid4(),
            run_id=run.id,
            step_name="test_step",
            step_type="other",
            index=0,
            started_at=datetime.now(timezone.utc),
        )
        session.add(step)
        await session.commit()

        step_id = step.id

        # Delete the run
        await session.delete(run)
        await session.commit()

        # Step should also be deleted
        result = await session.get(Step, step_id)
        assert result is None


class TestIndexes:
    """Tests for database indexes."""

    async def test_run_indexes_exist(self, engine) -> None:
        """Run table has expected indexes."""
        async with engine.begin() as conn:
            indexes = await conn.run_sync(
                lambda sync_conn: {
                    idx["name"] for idx in inspect(sync_conn).get_indexes("runs")
                }
            )

        expected_indexes = {
            "ix_runs_pipeline_name",
            "ix_runs_status",
            "ix_runs_started_at",
            "ix_runs_request_id",
            "ix_runs_user_id",
            "ix_runs_environment",
        }

        for idx in expected_indexes:
            assert idx in indexes, f"Missing index: {idx}"

    async def test_step_indexes_exist(self, engine) -> None:
        """Step table has expected indexes."""
        async with engine.begin() as conn:
            indexes = await conn.run_sync(
                lambda sync_conn: {
                    idx["name"] for idx in inspect(sync_conn).get_indexes("steps")
                }
            )

        expected_indexes = {
            "ix_steps_run_id",
            "ix_steps_step_name",
            "ix_steps_step_type",
            "ix_steps_input_count",
            "ix_steps_output_count",
            "ix_steps_status",
        }

        for idx in expected_indexes:
            assert idx in indexes, f"Missing index: {idx}"


class TestPayloadModel:
    """Tests for Payload model."""

    async def test_payload_creates_with_required_fields(self, session: AsyncSession) -> None:
        """Payload model creates with required fields."""
        # Create run first
        run = Run(
            id=uuid4(),
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

        payload = Payload(
            run_id=run.id,
            step_id=None,
            ref_id="p-001",
            phase="input",
            data=[1, 2, 3, 4, 5],
        )
        session.add(payload)
        await session.commit()
        await session.refresh(payload)

        assert payload.id is not None
        assert payload.run_id == run.id
        assert payload.step_id is None
        assert payload.ref_id == "p-001"
        assert payload.phase == "input"
        assert payload.data == [1, 2, 3, 4, 5]

    async def test_payload_linked_to_step(self, session: AsyncSession) -> None:
        """Payload can be linked to a step."""
        run = Run(
            id=uuid4(),
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

        step = Step(
            id=uuid4(),
            run_id=run.id,
            step_name="filter",
            step_type="filter",
            index=0,
            started_at=datetime.now(timezone.utc),
        )
        session.add(step)
        await session.commit()

        payload = Payload(
            run_id=run.id,
            step_id=step.id,
            ref_id="p-002",
            phase="output",
            data={"large": "object", "items": list(range(100))},
        )
        session.add(payload)
        await session.commit()
        await session.refresh(payload)

        assert payload.step_id == step.id
        assert payload.phase == "output"
        assert len(payload.data["items"]) == 100

    async def test_payload_cascade_delete_with_run(self, session: AsyncSession) -> None:
        """Payloads are deleted when run is deleted."""
        run = Run(
            id=uuid4(),
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

        payload = Payload(
            run_id=run.id,
            ref_id="p-003",
            phase="input",
            data="large string data",
        )
        session.add(payload)
        await session.commit()

        payload_id = payload.id

        # Expunge to remove from session cache
        session.expunge(payload)
        session.expunge(run)

        # Re-fetch run to delete
        run_to_delete = await session.get(Run, run.id)
        await session.delete(run_to_delete)
        await session.commit()

        # Query database directly (not using get which may return cached)
        stmt = select(Payload).where(Payload.id == payload_id)
        result = await session.execute(stmt)
        assert result.scalar_one_or_none() is None
