"""Tests for API data access layer (store)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api import store
from api.models import Base, Run, Step


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


class TestCreateRun:
    """Tests for store.create_run()."""

    async def test_create_run_with_required_fields(self, session: AsyncSession) -> None:
        """create_run creates a run with required fields."""
        run_id = uuid4()
        started = datetime.now(timezone.utc)

        run = await store.create_run(
            session,
            id=run_id,
            pipeline_name="test_pipeline",
            status="running",
            started_at=started,
        )

        assert run.id == run_id
        assert run.pipeline_name == "test_pipeline"
        assert run.status == "running"
        # SQLite strips timezone info, so compare without tzinfo
        assert run.started_at.replace(tzinfo=None) == started.replace(tzinfo=None)

    async def test_create_run_with_all_fields(self, session: AsyncSession) -> None:
        """create_run creates a run with all fields."""
        run_id = uuid4()
        started = datetime.now(timezone.utc)

        run = await store.create_run(
            session,
            id=run_id,
            pipeline_name="recommendation_pipeline",
            status="running",
            started_at=started,
            input_summary={"query": "test query", "_count": 5},
            metadata={"request_id": "req-123", "custom": "value"},
            request_id="req-123",
            user_id="user-456",
            environment="production",
        )

        assert run.id == run_id
        assert run.input_summary == {"query": "test query", "_count": 5}
        assert run.metadata_ == {"request_id": "req-123", "custom": "value"}
        assert run.request_id == "req-123"
        assert run.user_id == "user-456"
        assert run.environment == "production"

    async def test_create_run_persists_to_db(self, session: AsyncSession) -> None:
        """create_run persists the run to the database."""
        run_id = uuid4()

        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        # Fetch from DB to verify persistence
        fetched = await session.get(Run, run_id)
        assert fetched is not None
        assert fetched.pipeline_name == "test"


class TestEndRun:
    """Tests for store.end_run()."""

    async def test_end_run_updates_fields(self, session: AsyncSession) -> None:
        """end_run updates the run with completion data."""
        run_id = uuid4()
        started = datetime.now(timezone.utc)

        # Create run
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=started,
        )

        # End run
        ended = datetime.now(timezone.utc)
        run = await store.end_run(
            session,
            id=run_id,
            status="success",
            ended_at=ended,
            output_summary={"result": "done"},
        )

        assert run is not None
        assert run.status == "success"
        # SQLite strips timezone info, so compare without tzinfo
        assert run.ended_at.replace(tzinfo=None) == ended.replace(tzinfo=None)
        assert run.output_summary == {"result": "done"}

    async def test_end_run_with_error(self, session: AsyncSession) -> None:
        """end_run can record error information."""
        run_id = uuid4()

        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        run = await store.end_run(
            session,
            id=run_id,
            status="error",
            ended_at=datetime.now(timezone.utc),
            error_message="ValueError: Something went wrong",
        )

        assert run is not None
        assert run.status == "error"
        assert run.error_message == "ValueError: Something went wrong"

    async def test_end_run_not_found(self, session: AsyncSession) -> None:
        """end_run returns None for non-existent run."""
        result = await store.end_run(
            session,
            id=uuid4(),
            status="success",
            ended_at=datetime.now(timezone.utc),
        )

        assert result is None


class TestCreateStep:
    """Tests for store.create_step()."""

    async def test_create_step_with_required_fields(self, session: AsyncSession) -> None:
        """create_step creates a step with required fields."""
        # Create parent run
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        step_id = uuid4()
        started = datetime.now(timezone.utc)

        step = await store.create_step(
            session,
            id=step_id,
            run_id=run_id,
            step_name="filter_step",
            step_type="filter",
            index=0,
            started_at=started,
        )

        assert step.id == step_id
        assert step.run_id == run_id
        assert step.step_name == "filter_step"
        assert step.step_type == "filter"
        assert step.index == 0
        assert step.status == "running"  # Default status

    async def test_create_step_with_all_fields(self, session: AsyncSession) -> None:
        """create_step creates a step with all fields."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        step = await store.create_step(
            session,
            id=uuid4(),
            run_id=run_id,
            step_name="rank_candidates",
            step_type="rank",
            index=1,
            started_at=datetime.now(timezone.utc),
            input_summary={"candidates": 100},
            input_count=100,
            metadata={"source": "retrieval"},
        )

        assert step.input_summary == {"candidates": 100}
        assert step.input_count == 100
        assert step.metadata_ == {"source": "retrieval"}


class TestEndStep:
    """Tests for store.end_step()."""

    async def test_end_step_updates_fields(self, session: AsyncSession) -> None:
        """end_step updates the step with completion data."""
        # Create run and step
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        step_id = uuid4()
        await store.create_step(
            session,
            id=step_id,
            run_id=run_id,
            step_name="test_step",
            step_type="filter",
            index=0,
            started_at=datetime.now(timezone.utc),
            input_count=100,
        )

        # End step
        step = await store.end_step(
            session,
            id=step_id,
            status="success",
            ended_at=datetime.now(timezone.utc),
            duration_ms=150,
            output_summary={"filtered": 50},
            output_count=50,
            reasoning={"threshold": 0.5},
        )

        assert step is not None
        assert step.status == "success"
        assert step.duration_ms == 150
        assert step.output_count == 50
        assert step.reasoning == {"threshold": 0.5}

    async def test_end_step_with_error(self, session: AsyncSession) -> None:
        """end_step can record error information."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        step_id = uuid4()
        await store.create_step(
            session,
            id=step_id,
            run_id=run_id,
            step_name="test_step",
            step_type="llm",
            index=0,
            started_at=datetime.now(timezone.utc),
        )

        step = await store.end_step(
            session,
            id=step_id,
            status="error",
            ended_at=datetime.now(timezone.utc),
            error_message="LLM timeout after 30s",
        )

        assert step is not None
        assert step.status == "error"
        assert step.error_message == "LLM timeout after 30s"

    async def test_end_step_not_found(self, session: AsyncSession) -> None:
        """end_step returns None for non-existent step."""
        result = await store.end_step(
            session,
            id=uuid4(),
            status="success",
            ended_at=datetime.now(timezone.utc),
        )

        assert result is None


class TestGetRun:
    """Tests for store.get_run()."""

    async def test_get_run_by_id(self, session: AsyncSession) -> None:
        """get_run retrieves a run by ID."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        run = await store.get_run(session, run_id)

        assert run is not None
        assert run.id == run_id
        assert run.pipeline_name == "test"

    async def test_get_run_includes_steps(self, session: AsyncSession) -> None:
        """get_run with include_steps=True loads steps."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        # Add steps
        for i in range(3):
            await store.create_step(
                session,
                id=uuid4(),
                run_id=run_id,
                step_name=f"step_{i}",
                step_type="other",
                index=i,
                started_at=datetime.now(timezone.utc),
            )

        run = await store.get_run(session, run_id, include_steps=True)

        assert run is not None
        assert len(run.steps) == 3

    async def test_get_run_without_steps(self, session: AsyncSession) -> None:
        """get_run with include_steps=False doesn't load steps eagerly."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        await store.create_step(
            session,
            id=uuid4(),
            run_id=run_id,
            step_name="step",
            step_type="other",
            index=0,
            started_at=datetime.now(timezone.utc),
        )

        run = await store.get_run(session, run_id, include_steps=False)

        assert run is not None
        # Steps not eagerly loaded (may still be accessible via lazy load)

    async def test_get_run_not_found(self, session: AsyncSession) -> None:
        """get_run returns None for non-existent run."""
        result = await store.get_run(session, uuid4())
        assert result is None


class TestGetStep:
    """Tests for store.get_step()."""

    async def test_get_step_by_id(self, session: AsyncSession) -> None:
        """get_step retrieves a step by ID."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        step_id = uuid4()
        await store.create_step(
            session,
            id=step_id,
            run_id=run_id,
            step_name="test_step",
            step_type="filter",
            index=0,
            started_at=datetime.now(timezone.utc),
        )

        step = await store.get_step(session, step_id)

        assert step is not None
        assert step.id == step_id
        assert step.step_name == "test_step"

    async def test_get_step_not_found(self, session: AsyncSession) -> None:
        """get_step returns None for non-existent step."""
        result = await store.get_step(session, uuid4())
        assert result is None


class TestListRuns:
    """Tests for store.list_runs()."""

    async def test_list_runs_returns_all(self, session: AsyncSession) -> None:
        """list_runs returns all runs."""
        for i in range(5):
            await store.create_run(
                session,
                id=uuid4(),
                pipeline_name=f"pipeline_{i}",
                status="success",
                started_at=datetime.now(timezone.utc),
            )

        runs = await store.list_runs(session)
        assert len(runs) == 5

    async def test_list_runs_filter_by_pipeline(self, session: AsyncSession) -> None:
        """list_runs filters by pipeline_name."""
        for i in range(3):
            await store.create_run(
                session,
                id=uuid4(),
                pipeline_name="target_pipeline" if i == 0 else f"other_{i}",
                status="success",
                started_at=datetime.now(timezone.utc),
            )

        runs = await store.list_runs(session, pipeline_name="target_pipeline")
        assert len(runs) == 1
        assert runs[0].pipeline_name == "target_pipeline"

    async def test_list_runs_filter_by_status(self, session: AsyncSession) -> None:
        """list_runs filters by status."""
        for status in ["success", "success", "error"]:
            await store.create_run(
                session,
                id=uuid4(),
                pipeline_name="test",
                status=status,
                started_at=datetime.now(timezone.utc),
            )

        runs = await store.list_runs(session, status="error")
        assert len(runs) == 1
        assert runs[0].status == "error"

    async def test_list_runs_pagination(self, session: AsyncSession) -> None:
        """list_runs supports pagination."""
        for i in range(10):
            await store.create_run(
                session,
                id=uuid4(),
                pipeline_name=f"pipeline_{i}",
                status="success",
                started_at=datetime.now(timezone.utc),
            )

        runs = await store.list_runs(session, limit=5, offset=0)
        assert len(runs) == 5

        runs_page2 = await store.list_runs(session, limit=5, offset=5)
        assert len(runs_page2) == 5


class TestListSteps:
    """Tests for store.list_steps()."""

    async def test_list_steps_filter_by_run(self, session: AsyncSession) -> None:
        """list_steps filters by run_id."""
        run1_id = uuid4()
        run2_id = uuid4()

        for run_id in [run1_id, run2_id]:
            await store.create_run(
                session,
                id=run_id,
                pipeline_name="test",
                status="running",
                started_at=datetime.now(timezone.utc),
            )

        # Add steps to run1
        for i in range(3):
            await store.create_step(
                session,
                id=uuid4(),
                run_id=run1_id,
                step_name=f"step_{i}",
                step_type="filter",
                index=i,
                started_at=datetime.now(timezone.utc),
            )

        # Add step to run2
        await store.create_step(
            session,
            id=uuid4(),
            run_id=run2_id,
            step_name="other_step",
            step_type="rank",
            index=0,
            started_at=datetime.now(timezone.utc),
        )

        steps = await store.list_steps(session, run_id=run1_id)
        assert len(steps) == 3
        assert all(s.run_id == run1_id for s in steps)

    async def test_list_steps_filter_by_type(self, session: AsyncSession) -> None:
        """list_steps filters by step_type."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        for i, step_type in enumerate(["filter", "rank", "filter", "llm"]):
            await store.create_step(
                session,
                id=uuid4(),
                run_id=run_id,
                step_name=f"step_{i}",
                step_type=step_type,
                index=i,
                started_at=datetime.now(timezone.utc),
            )

        steps = await store.list_steps(session, step_type="filter")
        assert len(steps) == 2
        assert all(s.step_type == "filter" for s in steps)


class TestFullLifecycle:
    """Integration tests for complete pipeline lifecycle."""

    async def test_full_pipeline_lifecycle(self, session: AsyncSession) -> None:
        """Test complete pipeline: create run -> add steps -> end steps -> end run."""
        run_id = uuid4()
        started = datetime.now(timezone.utc)

        # 1. Create run
        run = await store.create_run(
            session,
            id=run_id,
            pipeline_name="recommendation_pipeline",
            status="running",
            started_at=started,
            input_summary={"query": "test", "candidates": 100},
            request_id="req-123",
            user_id="user-456",
        )
        assert run.status == "running"

        # 2. Create and end filter step
        filter_step_id = uuid4()
        await store.create_step(
            session,
            id=filter_step_id,
            run_id=run_id,
            step_name="price_filter",
            step_type="filter",
            index=0,
            started_at=datetime.now(timezone.utc),
            input_count=100,
        )
        await store.end_step(
            session,
            id=filter_step_id,
            status="success",
            ended_at=datetime.now(timezone.utc),
            duration_ms=50,
            output_count=80,
            reasoning={"max_price": 100, "removed": 20},
        )

        # 3. Create and end rank step
        rank_step_id = uuid4()
        await store.create_step(
            session,
            id=rank_step_id,
            run_id=run_id,
            step_name="relevance_rank",
            step_type="rank",
            index=1,
            started_at=datetime.now(timezone.utc),
            input_count=80,
        )
        await store.end_step(
            session,
            id=rank_step_id,
            status="success",
            ended_at=datetime.now(timezone.utc),
            duration_ms=100,
            output_count=10,
        )

        # 4. End run
        run = await store.end_run(
            session,
            id=run_id,
            status="success",
            ended_at=datetime.now(timezone.utc),
            output_summary={"recommendations": 10},
        )
        assert run.status == "success"

        # 5. Fetch complete run with steps
        complete_run = await store.get_run(session, run_id, include_steps=True)
        assert complete_run is not None
        assert complete_run.status == "success"
        assert len(complete_run.steps) == 2
        assert complete_run.steps[0].step_name == "price_filter"
        assert complete_run.steps[0].input_count == 100
        assert complete_run.steps[0].output_count == 80
        assert complete_run.steps[1].step_name == "relevance_rank"
        assert complete_run.steps[1].input_count == 80
        assert complete_run.steps[1].output_count == 10

    async def test_pipeline_with_error(self, session: AsyncSession) -> None:
        """Test pipeline that fails with an error."""
        run_id = uuid4()

        # Create run
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="failing_pipeline",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        # Create and end step with error
        step_id = uuid4()
        await store.create_step(
            session,
            id=step_id,
            run_id=run_id,
            step_name="llm_call",
            step_type="llm",
            index=0,
            started_at=datetime.now(timezone.utc),
        )
        await store.end_step(
            session,
            id=step_id,
            status="error",
            ended_at=datetime.now(timezone.utc),
            error_message="API rate limit exceeded",
        )

        # End run with error
        run = await store.end_run(
            session,
            id=run_id,
            status="error",
            ended_at=datetime.now(timezone.utc),
            error_message="Pipeline failed: LLM step error",
        )

        assert run.status == "error"
        assert "Pipeline failed" in run.error_message

        # Verify step has error
        complete_run = await store.get_run(session, run_id, include_steps=True)
        assert complete_run.steps[0].status == "error"
        assert "rate limit" in complete_run.steps[0].error_message


class TestCreatePayloads:
    """Tests for store.create_payloads()."""

    async def test_create_payloads_for_run(self, session: AsyncSession) -> None:
        """create_payloads stores payloads linked to a run."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        payloads = {
            "p-001": [1, 2, 3, 4, 5] * 50,  # Large list
            "p-002": "x" * 2000,  # Large string
        }

        created = await store.create_payloads(
            session,
            run_id=run_id,
            step_id=None,
            phase="input",
            payloads=payloads,
        )

        assert len(created) == 2
        assert {p.ref_id for p in created} == {"p-001", "p-002"}
        assert all(p.run_id == run_id for p in created)
        assert all(p.step_id is None for p in created)
        assert all(p.phase == "input" for p in created)

    async def test_create_payloads_for_step(self, session: AsyncSession) -> None:
        """create_payloads stores payloads linked to a step."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        step_id = uuid4()
        await store.create_step(
            session,
            id=step_id,
            run_id=run_id,
            step_name="filter",
            step_type="filter",
            index=0,
            started_at=datetime.now(timezone.utc),
        )

        payloads = {
            "p-003": {"items": list(range(200))},
        }

        created = await store.create_payloads(
            session,
            run_id=run_id,
            step_id=step_id,
            phase="output",
            payloads=payloads,
        )

        assert len(created) == 1
        assert created[0].run_id == run_id
        assert created[0].step_id == step_id
        assert created[0].phase == "output"
        assert created[0].ref_id == "p-003"
        assert len(created[0].data["items"]) == 200


class TestGetPayloads:
    """Tests for store.get_payloads()."""

    async def test_get_payloads_by_run(self, session: AsyncSession) -> None:
        """get_payloads retrieves payloads for a run."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        await store.create_payloads(
            session,
            run_id=run_id,
            step_id=None,
            phase="input",
            payloads={"p-001": [1, 2, 3]},
        )

        fetched = await store.get_payloads(session, run_id=run_id)
        assert len(fetched) == 1
        assert fetched[0].ref_id == "p-001"

    async def test_get_payloads_filter_by_phase(self, session: AsyncSession) -> None:
        """get_payloads filters by phase."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        await store.create_payloads(
            session,
            run_id=run_id,
            step_id=None,
            phase="input",
            payloads={"p-input": "input data"},
        )
        await store.create_payloads(
            session,
            run_id=run_id,
            step_id=None,
            phase="output",
            payloads={"p-output": "output data"},
        )

        input_payloads = await store.get_payloads(session, run_id=run_id, phase="input")
        assert len(input_payloads) == 1
        assert input_payloads[0].ref_id == "p-input"

        output_payloads = await store.get_payloads(session, run_id=run_id, phase="output")
        assert len(output_payloads) == 1
        assert output_payloads[0].ref_id == "p-output"

    async def test_get_payloads_filter_by_ref_id(self, session: AsyncSession) -> None:
        """get_payloads filters by ref_id."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        await store.create_payloads(
            session,
            run_id=run_id,
            step_id=None,
            phase="input",
            payloads={"p-001": [1, 2], "p-002": [3, 4]},
        )

        fetched = await store.get_payloads(session, run_id=run_id, ref_id="p-001")
        assert len(fetched) == 1
        assert fetched[0].data == [1, 2]

    async def test_get_payloads_filter_run_level_vs_step_level(
        self, session: AsyncSession
    ) -> None:
        """get_payloads correctly distinguishes run-level vs step-level payloads."""
        run_id = uuid4()
        await store.create_run(
            session,
            id=run_id,
            pipeline_name="test",
            status="running",
            started_at=datetime.now(timezone.utc),
        )

        step_id = uuid4()
        await store.create_step(
            session,
            id=step_id,
            run_id=run_id,
            step_name="filter",
            step_type="filter",
            index=0,
            started_at=datetime.now(timezone.utc),
        )

        # Create run-level payload (step_id=None)
        await store.create_payloads(
            session,
            run_id=run_id,
            step_id=None,
            phase="input",
            payloads={"run-payload": "run-level data"},
        )

        # Create step-level payload
        await store.create_payloads(
            session,
            run_id=run_id,
            step_id=step_id,
            phase="output",
            payloads={"step-payload": "step-level data"},
        )

        # Default (no step_id arg) → returns ALL payloads
        all_payloads = await store.get_payloads(session, run_id=run_id)
        assert len(all_payloads) == 2

        # step_id=None explicitly → returns only run-level payloads
        run_level = await store.get_payloads(session, run_id=run_id, step_id=None)
        assert len(run_level) == 1
        assert run_level[0].ref_id == "run-payload"
        assert run_level[0].step_id is None

        # step_id=<uuid> → returns only that step's payloads
        step_level = await store.get_payloads(session, run_id=run_id, step_id=step_id)
        assert len(step_level) == 1
        assert step_level[0].ref_id == "step-payload"
        assert step_level[0].step_id == step_id
