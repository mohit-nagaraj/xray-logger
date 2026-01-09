"""Tests for SDK Run class."""

from unittest.mock import Mock

import pytest

from sdk.run import Run
from sdk.step import LARGE_LIST_THRESHOLD
from shared.types import RunStatus, StepType


class TestRun:
    """Tests for Run class."""

    @pytest.fixture
    def mock_transport(self):
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    def test_run_generates_uuid(self, mock_transport) -> None:
        run = Run(mock_transport, "test_pipeline")
        assert len(run.id) == 36  # UUID format

    def test_run_properties(self, mock_transport) -> None:
        run = Run(mock_transport, "my_pipeline")
        assert run.pipeline_name == "my_pipeline"
        assert run.status == RunStatus.running
        assert run.metadata == {}

    def test_run_sends_start_event(self, mock_transport) -> None:
        Run(mock_transport, "test_pipeline")

        mock_transport.send.assert_called_once()
        event = mock_transport.send.call_args[0][0]
        assert event["event_type"] == "run_start"
        assert event["pipeline_name"] == "test_pipeline"
        assert event["status"] == "running"

    def test_run_with_input_data(self, mock_transport) -> None:
        run = Run(
            mock_transport,
            "test_pipeline",
            input_data={"query": "test query", "user_id": "u-123"},
        )

        event = mock_transport.send.call_args[0][0]
        assert event["input_summary"] is not None
        assert event["input_summary"]["_type"] == "dict"

    def test_run_with_metadata(self, mock_transport) -> None:
        run = Run(
            mock_transport,
            "test_pipeline",
            metadata={"request_id": "req-123", "user_id": "u-456", "environment": "prod"},
        )

        event = mock_transport.send.call_args[0][0]
        assert event["metadata"]["request_id"] == "req-123"
        # Common fields should be flattened to top level
        assert event["request_id"] == "req-123"
        assert event["user_id"] == "u-456"
        assert event["environment"] == "prod"

    def test_run_end_sends_event(self, mock_transport) -> None:
        run = Run(mock_transport, "test_pipeline")
        run.end(output={"result": "success"})

        assert mock_transport.send.call_count == 2
        end_event = mock_transport.send.call_args_list[1][0][0]
        assert end_event["event_type"] == "run_end"
        assert end_event["status"] == "success"
        assert end_event["output_summary"] is not None

    def test_run_end_is_idempotent(self, mock_transport) -> None:
        run = Run(mock_transport, "test_pipeline")
        run.end()
        run.end()  # Second call should be ignored

        assert mock_transport.send.call_count == 2  # Only start + one end

    def test_run_end_with_error(self, mock_transport) -> None:
        run = Run(mock_transport, "test_pipeline")
        run.end_with_error(ValueError("pipeline failed"))

        end_event = mock_transport.send.call_args_list[1][0][0]
        assert end_event["status"] == "error"
        assert "ValueError" in end_event["error_message"]

    def test_run_end_with_error_string(self, mock_transport) -> None:
        run = Run(mock_transport, "test_pipeline")
        run.end_with_error("custom error")

        end_event = mock_transport.send.call_args_list[1][0][0]
        assert end_event["error_message"] == "custom error"

    def test_run_start_step_creates_step(self, mock_transport) -> None:
        run = Run(mock_transport, "test_pipeline")
        step = run.start_step("filter", StepType.filter, [1, 2, 3])

        assert step.run_id == run.id
        assert step.name == "filter"

    def test_run_step_index_increments(self, mock_transport) -> None:
        run = Run(mock_transport, "test_pipeline")
        step1 = run.start_step("step1", StepType.filter, [])
        step2 = run.start_step("step2", StepType.rank, [])

        assert step1._index == 0
        assert step2._index == 1

    def test_run_start_step_with_string_type(self, mock_transport) -> None:
        run = Run(mock_transport, "test_pipeline")
        step = run.start_step("llm_step", "llm", [])

        assert step.step_type == StepType.llm

    def test_run_context_manager_success(self, mock_transport) -> None:
        with Run(mock_transport, "test_pipeline") as run:
            step = run.start_step("test", StepType.other, [])
            step.end([])

        # Should have: run_start, step_start, step_end, run_end
        assert mock_transport.send.call_count == 4
        final_event = mock_transport.send.call_args_list[-1][0][0]
        assert final_event["status"] == "success"

    def test_run_context_manager_error(self, mock_transport) -> None:
        with pytest.raises(ValueError):
            with Run(mock_transport, "test_pipeline") as run:
                raise ValueError("test error")

        end_event = mock_transport.send.call_args_list[-1][0][0]
        assert end_event["status"] == "error"
        assert "ValueError" in end_event["error_message"]

    def test_run_context_manager_does_not_suppress_exception(self, mock_transport) -> None:
        with pytest.raises(RuntimeError):
            with Run(mock_transport, "test_pipeline"):
                raise RuntimeError("should propagate")

    def test_run_status_from_string(self, mock_transport) -> None:
        run = Run(mock_transport, "test_pipeline")
        run.end(status="error")

        end_event = mock_transport.send.call_args_list[-1][0][0]
        assert end_event["status"] == "error"


class TestRunIntegration:
    """Integration tests for Run with Steps."""

    @pytest.fixture
    def mock_transport(self):
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    def test_full_pipeline_flow(self, mock_transport) -> None:
        """Test a complete pipeline with multiple steps."""
        candidates = [
            {"id": "1", "score": 0.9},
            {"id": "2", "score": 0.8},
            {"id": "3", "score": 0.7},
        ]

        with Run(mock_transport, "recommendation_pipeline") as run:
            # Filter step
            step1 = run.start_step("price_filter", StepType.filter, candidates)
            filtered = [{"id": "1", "score": 0.9, "reason": "passed"}, {"id": "2", "score": 0.8, "reason": "passed"}]
            step1.attach_reasoning({"threshold": 100})
            step1.end(filtered)

            # Rank step
            step2 = run.start_step("relevance_rank", StepType.rank, filtered)
            ranked = [{"id": "2", "score": 0.95, "reason": "best match"}, {"id": "1", "score": 0.85}]
            step2.end(ranked)

        # Verify all events were sent
        # run_start, step1_start, step1_end, step2_start, step2_end, run_end
        assert mock_transport.send.call_count == 6

        # Verify step indices
        step1_start = mock_transport.send.call_args_list[1][0][0]
        step2_start = mock_transport.send.call_args_list[3][0][0]
        assert step1_start["index"] == 0
        assert step2_start["index"] == 1

    def test_pipeline_with_error_step(self, mock_transport) -> None:
        """Test pipeline where a step fails."""
        with pytest.raises(RuntimeError):
            with Run(mock_transport, "failing_pipeline") as run:
                step = run.start_step("failing_step", StepType.llm, [])
                step.end_with_error("LLM timeout")
                raise RuntimeError("Step failed")

        # Find the step end event
        step_end = None
        run_end = None
        for call in mock_transport.send.call_args_list:
            event = call[0][0]
            if event["event_type"] == "step_end":
                step_end = event
            if event["event_type"] == "run_end":
                run_end = event

        assert step_end["status"] == "error"
        assert run_end["status"] == "error"


class TestRunPayloads:
    """Tests for Run class with _payloads."""

    @pytest.fixture
    def mock_transport(self):
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    def test_run_start_event_includes_payloads(self, mock_transport) -> None:
        """Run start event includes _payloads field."""
        Run(mock_transport, "test_pipeline", input_data={"query": "test"})

        start_event = mock_transport.send.call_args[0][0]
        assert "_payloads" in start_event
        # Small input, no externalization
        assert start_event["_payloads"] is None

    def test_run_start_with_large_input_has_payloads(self, mock_transport) -> None:
        """Run start event with large input has _payloads."""
        large_input = {"data": list(range(LARGE_LIST_THRESHOLD + 10))}
        Run(mock_transport, "test_pipeline", input_data=large_input)

        start_event = mock_transport.send.call_args[0][0]
        assert start_event["_payloads"] is not None

    def test_run_end_event_includes_payloads(self, mock_transport) -> None:
        """Run end event includes _payloads field."""
        run = Run(mock_transport, "test_pipeline")
        run.end(output={"result": "success"})

        end_event = mock_transport.send.call_args_list[1][0][0]
        assert "_payloads" in end_event

    def test_run_end_with_large_output_has_payloads(self, mock_transport) -> None:
        """Run end event with large output has _payloads."""
        run = Run(mock_transport, "test_pipeline")
        large_output = {"results": list(range(LARGE_LIST_THRESHOLD + 10))}
        run.end(output=large_output)

        end_event = mock_transport.send.call_args_list[1][0][0]
        assert end_event["_payloads"] is not None

    def test_run_end_with_error_includes_payloads(self, mock_transport) -> None:
        """Run end_with_error includes _payloads field."""
        run = Run(mock_transport, "test_pipeline")
        run.end_with_error(ValueError("test error"), output={"partial": "result"})

        end_event = mock_transport.send.call_args_list[1][0][0]
        assert "_payloads" in end_event
