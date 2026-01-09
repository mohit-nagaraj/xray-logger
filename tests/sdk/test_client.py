"""Tests for SDK client and context management."""

import asyncio
from unittest.mock import Mock, patch

import pytest

from sdk.client import (
    XRayClient,
    _current_run,
    current_run,
    current_step,
    get_client,
    init_xray,
    shutdown_xray,
)
from sdk.config import XRayConfig
from shared.types import StepType


class TestXRayClientInit:
    """Tests for XRayClient initialization."""

    def test_client_init_with_config(self) -> None:
        """Client initializes with config."""
        config = XRayConfig(base_url="http://localhost:8000")
        client = XRayClient(config)

        assert client.config == config
        assert not client.is_started

    def test_client_init_creates_transport(self) -> None:
        """Client creates Transport instance."""
        config = XRayConfig(base_url="http://localhost:8000")
        client = XRayClient(config)

        assert client._transport is not None


class TestXRayClientStart:
    """Tests for XRayClient.start()."""

    def test_start_sets_started_flag(self) -> None:
        """Start sets is_started to True."""
        config = XRayConfig(base_url=None)  # No actual HTTP
        client = XRayClient(config)

        client.start()
        assert client.is_started

        client.shutdown()

    def test_start_is_idempotent(self) -> None:
        """Calling start twice is safe."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)

        client.start()
        client.start()  # Should not raise
        assert client.is_started

        client.shutdown()

    def test_start_creates_background_thread(self) -> None:
        """Start creates background thread."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)

        client.start()

        assert client._thread is not None
        assert client._thread.is_alive()
        assert client._thread.name == "xray-transport"

        client.shutdown()

    def test_start_creates_event_loop(self) -> None:
        """Start creates asyncio event loop."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)

        client.start()

        assert client._loop is not None
        assert client._loop.is_running()

        client.shutdown()


class TestXRayClientShutdown:
    """Tests for XRayClient.shutdown()."""

    def test_shutdown_sets_started_false(self) -> None:
        """Shutdown sets is_started to False."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)

        client.start()
        assert client.is_started

        client.shutdown()
        assert not client.is_started

    def test_shutdown_is_idempotent(self) -> None:
        """Calling shutdown twice is safe."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)

        client.start()
        client.shutdown()
        client.shutdown()  # Should not raise

        assert not client.is_started

    def test_shutdown_without_start(self) -> None:
        """Shutdown without start is safe."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)

        client.shutdown()  # Should not raise
        assert not client.is_started

    def test_shutdown_stops_thread(self) -> None:
        """Shutdown stops background thread."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)

        client.start()
        thread = client._thread

        client.shutdown()

        assert not thread.is_alive()


class TestStartRun:
    """Tests for XRayClient.start_run() context manager."""

    @pytest.fixture
    def client(self):
        """Create a started client for testing."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client.start()
        yield client
        client.shutdown()

    def test_start_run_returns_run(self, client: XRayClient) -> None:
        """start_run yields a Run instance."""
        with client.start_run("test_pipeline") as run:
            assert run is not None
            assert run.pipeline_name == "test_pipeline"

    def test_start_run_sets_context(self, client: XRayClient) -> None:
        """start_run sets current run context."""
        with client.start_run("test_pipeline") as run:
            assert current_run() is run

    def test_start_run_resets_context_after_exit(self, client: XRayClient) -> None:
        """Context resets to None after context manager exits."""
        with client.start_run("test_pipeline"):
            pass

        assert current_run() is None

    def test_start_run_with_input_data(self, client: XRayClient) -> None:
        """start_run accepts input_data."""
        with client.start_run(
            "test_pipeline", input_data={"query": "test"}
        ) as run:
            assert run._input_summary is not None

    def test_start_run_with_metadata(self, client: XRayClient) -> None:
        """start_run accepts metadata."""
        with client.start_run(
            "test_pipeline", metadata={"request_id": "req-123"}
        ) as run:
            assert run.metadata["request_id"] == "req-123"

    def test_start_run_ends_run_on_exit(self, client: XRayClient) -> None:
        """Run is ended when context manager exits."""
        with client.start_run("test_pipeline") as run:
            assert run._ended_at is None

        assert run._ended_at is not None

    def test_start_run_handles_exception(self, client: XRayClient) -> None:
        """Run is marked as error on exception."""
        with pytest.raises(ValueError):
            with client.start_run("test_pipeline") as run:
                raise ValueError("test error")

        assert run.status.value == "error"
        assert run._error_message is not None
        assert "ValueError" in run._error_message

    def test_start_run_exception_propagates(self, client: XRayClient) -> None:
        """Exceptions propagate through context manager."""
        with pytest.raises(RuntimeError, match="should propagate"):
            with client.start_run("test_pipeline"):
                raise RuntimeError("should propagate")


class TestNestedRuns:
    """Tests for nested run support."""

    @pytest.fixture
    def client(self):
        """Create a started client for testing."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client.start()
        yield client
        client.shutdown()

    def test_nested_runs_inner_overrides(self, client: XRayClient) -> None:
        """Inner run becomes current run."""
        with client.start_run("outer") as outer_run:
            assert current_run() is outer_run

            with client.start_run("inner") as inner_run:
                assert current_run() is inner_run
                assert current_run() is not outer_run

    def test_nested_runs_outer_restored(self, client: XRayClient) -> None:
        """Outer run restored after inner exits."""
        with client.start_run("outer") as outer_run:
            with client.start_run("inner"):
                pass

            # After inner exits, outer should be restored
            assert current_run() is outer_run

    def test_deeply_nested_runs(self, client: XRayClient) -> None:
        """Multiple levels of nesting work correctly."""
        with client.start_run("level1") as run1:
            assert current_run() is run1

            with client.start_run("level2") as run2:
                assert current_run() is run2

                with client.start_run("level3") as run3:
                    assert current_run() is run3

                assert current_run() is run2

            assert current_run() is run1

        assert current_run() is None


class TestCurrentStep:
    """Tests for current_step() function."""

    @pytest.fixture
    def client(self):
        """Create a started client for testing."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client.start()
        yield client
        client.shutdown()

    def test_current_step_none_outside_run(self) -> None:
        """current_step returns None when no run is active."""
        assert current_step() is None

    def test_current_step_none_without_steps(self, client: XRayClient) -> None:
        """current_step returns None when run has no steps."""
        with client.start_run("test_pipeline"):
            assert current_step() is None

    def test_current_step_returns_active_step(self, client: XRayClient) -> None:
        """current_step returns the active (non-ended) step."""
        with client.start_run("test_pipeline") as run:
            step = run.start_step("my_step", StepType.filter, [1, 2, 3])
            assert current_step() is step

    def test_current_step_none_after_step_ends(self, client: XRayClient) -> None:
        """current_step returns None after step ends."""
        with client.start_run("test_pipeline") as run:
            step = run.start_step("my_step", StepType.filter, [1, 2, 3])
            step.end([1])

            assert current_step() is None

    def test_current_step_returns_latest_active(self, client: XRayClient) -> None:
        """current_step returns most recently started active step."""
        with client.start_run("test_pipeline") as run:
            step1 = run.start_step("step1", StepType.filter, [])
            step2 = run.start_step("step2", StepType.rank, [])

            # Both are active, should return step2 (latest)
            assert current_step() is step2

            step2.end([])
            # Now step1 is the only active step
            assert current_step() is step1


class TestGlobalFunctions:
    """Tests for global initialization functions."""

    def teardown_method(self) -> None:
        """Clean up global client after each test."""
        shutdown_xray()

    def test_init_xray_creates_client(self) -> None:
        """init_xray creates and starts global client."""
        client = init_xray(XRayConfig(base_url=None))

        assert client is not None
        assert client.is_started
        assert get_client() is client

    def test_init_xray_replaces_existing(self) -> None:
        """init_xray replaces existing client."""
        client1 = init_xray(XRayConfig(base_url=None))
        client2 = init_xray(XRayConfig(base_url=None))

        assert get_client() is client2
        assert get_client() is not client1

    def test_get_client_returns_none_before_init(self) -> None:
        """get_client returns None before init_xray."""
        assert get_client() is None

    def test_shutdown_xray_clears_client(self) -> None:
        """shutdown_xray clears global client."""
        init_xray(XRayConfig(base_url=None))
        shutdown_xray()

        assert get_client() is None

    def test_shutdown_xray_is_idempotent(self) -> None:
        """shutdown_xray can be called multiple times."""
        init_xray(XRayConfig(base_url=None))
        shutdown_xray()
        shutdown_xray()  # Should not raise

        assert get_client() is None


class TestContextVarsAsyncIsolation:
    """Tests for contextvars isolation across async tasks."""

    @pytest.fixture
    def client(self):
        """Create a started client for testing."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client.start()
        yield client
        client.shutdown()

    @pytest.mark.asyncio
    async def test_async_tasks_have_isolated_context(
        self, client: XRayClient
    ) -> None:
        """Concurrent async tasks have isolated run context."""
        results: dict[str, object] = {}

        async def task1() -> None:
            with client.start_run("pipeline1") as run:
                results["task1_run_id"] = run.id
                results["task1_current"] = current_run()
                await asyncio.sleep(0.1)
                results["task1_current_after_sleep"] = current_run()

        async def task2() -> None:
            # Wait a bit so task1 has started its run
            await asyncio.sleep(0.05)
            # task2 should see None, not task1's run
            results["task2_current"] = current_run()

        await asyncio.gather(task1(), task2())

        # Verify task1 saw its own run throughout
        assert results["task1_current"] is not None
        assert results["task1_current"].id == results["task1_run_id"]
        assert results["task1_current_after_sleep"] is results["task1_current"]

        # Verify task2 saw None (isolated from task1)
        assert results["task2_current"] is None

    @pytest.mark.asyncio
    async def test_async_tasks_with_own_runs(self, client: XRayClient) -> None:
        """Each async task can have its own run."""
        results: dict[str, str] = {}

        async def task_with_run(name: str) -> None:
            with client.start_run(f"pipeline_{name}") as run:
                results[f"{name}_run_id"] = run.id
                results[f"{name}_current_id"] = current_run().id
                await asyncio.sleep(0.05)

        await asyncio.gather(
            task_with_run("a"),
            task_with_run("b"),
            task_with_run("c"),
        )

        # Each task should have seen its own run
        assert results["a_run_id"] == results["a_current_id"]
        assert results["b_run_id"] == results["b_current_id"]
        assert results["c_run_id"] == results["c_current_id"]

        # All runs should be different
        assert len({results["a_run_id"], results["b_run_id"], results["c_run_id"]}) == 3


class TestContextVarsReset:
    """Tests for proper context variable reset."""

    def teardown_method(self) -> None:
        """Reset context variable after each test."""
        # Force reset the context variable
        _current_run.set(None)

    def test_context_reset_on_normal_exit(self) -> None:
        """Context resets properly on normal exit."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client.start()

        try:
            with client.start_run("test"):
                assert current_run() is not None

            assert current_run() is None
        finally:
            client.shutdown()

    def test_context_reset_on_exception(self) -> None:
        """Context resets properly even on exception."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client.start()

        try:
            with pytest.raises(ValueError):
                with client.start_run("test"):
                    raise ValueError("test")

            assert current_run() is None
        finally:
            client.shutdown()
