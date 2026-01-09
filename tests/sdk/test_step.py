"""Tests for SDK Step class and payload helpers."""

import time
from unittest.mock import Mock

import pytest

from sdk.step import (
    MAX_STRING_LENGTH,
    Step,
    extract_candidate,
    infer_count,
    is_candidate_list,
    summarize_payload,
)
from shared.types import StepStatus, StepType


class TestInferCount:
    """Tests for infer_count helper."""

    def test_list_returns_length(self) -> None:
        assert infer_count([1, 2, 3]) == 3

    def test_empty_list_returns_zero(self) -> None:
        assert infer_count([]) == 0

    def test_tuple_returns_length(self) -> None:
        assert infer_count((1, 2)) == 2

    def test_set_returns_length(self) -> None:
        assert infer_count({1, 2, 3}) == 3

    def test_dict_with_items_key(self) -> None:
        assert infer_count({"items": [1, 2, 3]}) == 3

    def test_dict_with_results_key(self) -> None:
        assert infer_count({"results": [1, 2]}) == 2

    def test_dict_with_data_key(self) -> None:
        assert infer_count({"data": [1, 2, 3, 4]}) == 4

    def test_dict_with_candidates_key(self) -> None:
        assert infer_count({"candidates": [1, 2, 3, 4, 5]}) == 5

    def test_plain_dict_returns_none(self) -> None:
        assert infer_count({"a": 1, "b": 2}) is None

    def test_string_returns_none(self) -> None:
        assert infer_count("hello") is None

    def test_int_returns_none(self) -> None:
        assert infer_count(42) is None

    def test_none_returns_none(self) -> None:
        assert infer_count(None) is None


class TestIsCandidateList:
    """Tests for is_candidate_list helper."""

    def test_list_of_dicts_with_id(self) -> None:
        items = [{"id": "1", "name": "a"}, {"id": "2", "name": "b"}]
        assert is_candidate_list(items) is True

    def test_list_of_dicts_with_underscore_id(self) -> None:
        items = [{"_id": "1"}, {"_id": "2"}]
        assert is_candidate_list(items) is True

    def test_list_of_dicts_with_candidate_id(self) -> None:
        items = [{"candidate_id": "1"}, {"candidate_id": "2"}]
        assert is_candidate_list(items) is True

    def test_empty_list_returns_false(self) -> None:
        assert is_candidate_list([]) is False

    def test_list_of_non_dicts_returns_false(self) -> None:
        assert is_candidate_list([1, 2, 3]) is False

    def test_list_of_dicts_without_id_returns_false(self) -> None:
        items = [{"name": "a"}, {"name": "b"}]
        assert is_candidate_list(items) is False

    def test_non_list_returns_false(self) -> None:
        assert is_candidate_list({"id": "1"}) is False
        assert is_candidate_list("hello") is False


class TestExtractCandidate:
    """Tests for extract_candidate helper."""

    def test_extracts_id(self) -> None:
        result = extract_candidate({"id": "123", "extra": "data"})
        assert result["id"] == "123"

    def test_extracts_underscore_id(self) -> None:
        result = extract_candidate({"_id": "456"})
        assert result["id"] == "456"

    def test_extracts_score(self) -> None:
        result = extract_candidate({"id": "1", "score": 0.95})
        assert result["score"] == 0.95

    def test_extracts_relevance_as_score(self) -> None:
        result = extract_candidate({"id": "1", "relevance": 0.8})
        assert result["score"] == 0.8

    def test_extracts_reason(self) -> None:
        result = extract_candidate({"id": "1", "reason": "passed filter"})
        assert result["reason"] == "passed filter"

    def test_extracts_explanation_as_reason(self) -> None:
        result = extract_candidate({"id": "1", "explanation": "good match"})
        assert result["reason"] == "good match"

    def test_reason_defaults_to_none(self) -> None:
        result = extract_candidate({"id": "1"})
        assert result["reason"] is None


class TestSummarizePayload:
    """Tests for summarize_payload helper."""

    def test_none_value(self) -> None:
        result = summarize_payload(None)
        assert result["_type"] == "null"
        assert result["_value"] is None

    def test_bool_value(self) -> None:
        result = summarize_payload(True)
        assert result["_type"] == "bool"
        assert result["_value"] is True

    def test_int_value(self) -> None:
        result = summarize_payload(42)
        assert result["_type"] == "int"
        assert result["_value"] == 42

    def test_float_value(self) -> None:
        result = summarize_payload(3.14)
        assert result["_type"] == "float"
        assert result["_value"] == 3.14

    def test_string_short(self) -> None:
        result = summarize_payload("hello")
        assert result["_type"] == "str"
        assert result["_value"] == "hello"
        assert result["_length"] == 5
        assert result["_truncated"] is False

    def test_string_long_truncated(self) -> None:
        long_string = "x" * 2000
        result = summarize_payload(long_string)
        assert result["_type"] == "str"
        assert result["_length"] == 2000
        assert result["_truncated"] is True
        assert len(result["_value"]) == MAX_STRING_LENGTH + 3  # +3 for "..."

    def test_bytes_value(self) -> None:
        result = summarize_payload(b"hello")
        assert result["_type"] == "bytes"
        assert result["_length"] == 5

    def test_candidate_list_extracts_all_ids(self) -> None:
        candidates = [
            {"id": "1", "score": 0.9, "name": "product1"},
            {"id": "2", "score": 0.8, "reason": "good match"},
            {"id": "3", "score": 0.7},
        ]
        result = summarize_payload(candidates)
        assert result["_type"] == "candidates"
        assert result["_count"] == 3
        assert len(result["_candidates"]) == 3
        assert result["_candidates"][0]["id"] == "1"
        assert result["_candidates"][0]["score"] == 0.9
        assert result["_candidates"][1]["reason"] == "good match"
        assert result["_candidates"][2]["reason"] is None

    def test_candidate_list_large_count(self) -> None:
        """Verify ALL candidates are captured, not just a sample."""
        candidates = [{"id": str(i), "score": i / 1000} for i in range(1000)]
        result = summarize_payload(candidates)
        assert result["_count"] == 1000
        assert len(result["_candidates"]) == 1000

    def test_non_candidate_list(self) -> None:
        items = [1, 2, 3, 4, 5]
        result = summarize_payload(items)
        assert result["_type"] == "list"
        assert result["_count"] == 5
        assert result["_item_type"] == "int"
        assert "_candidates" not in result

    def test_dict_captures_keys(self) -> None:
        data = {"query": "laptop", "user_id": "u-123", "filters": {"price": 1000}}
        result = summarize_payload(data)
        assert result["_type"] == "dict"
        assert result["_key_count"] == 3
        assert set(result["_keys"]) == {"query", "user_id", "filters"}

    def test_dict_captures_scalar_values(self) -> None:
        data = {"name": "test", "count": 5, "active": True}
        result = summarize_payload(data)
        assert result["_values"]["name"] == "test"
        assert result["_values"]["count"] == 5
        assert result["_values"]["active"] is True

    def test_nested_dict_shows_type(self) -> None:
        data = {"config": {"nested": "value"}}
        result = summarize_payload(data)
        assert result["_values"]["config"] == {"_type": "dict"}

    def test_max_depth_truncation(self) -> None:
        deep = {"l1": {"l2": {"l3": {"l4": {"l5": {"l6": "value"}}}}}}
        result = summarize_payload(deep, depth=0)
        # Should not crash and should handle depth
        assert "_type" in result


class TestStep:
    """Tests for Step class."""

    @pytest.fixture
    def mock_transport(self):
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def mock_run(self):
        run = Mock()
        run.id = "run-123"
        return run

    def test_step_generates_uuid(self, mock_run, mock_transport) -> None:
        step = Step(mock_run, mock_transport, "test", StepType.filter, [1, 2, 3], 0)
        assert len(step.id) == 36  # UUID format

    def test_step_properties(self, mock_run, mock_transport) -> None:
        step = Step(mock_run, mock_transport, "my_step", StepType.rank, [], 0)
        assert step.name == "my_step"
        assert step.step_type == StepType.rank
        assert step.run_id == "run-123"
        assert step.status == StepStatus.running

    def test_step_sends_start_event(self, mock_run, mock_transport) -> None:
        Step(mock_run, mock_transport, "test", StepType.filter, [1, 2, 3], 0)

        mock_transport.send.assert_called_once()
        event = mock_transport.send.call_args[0][0]
        assert event["event_type"] == "step_start"
        assert event["step_name"] == "test"
        assert event["step_type"] == "filter"
        assert event["input_count"] == 3
        assert event["index"] == 0

    def test_step_end_calculates_duration(self, mock_run, mock_transport) -> None:
        step = Step(mock_run, mock_transport, "test", StepType.filter, [], 0)
        time.sleep(0.01)  # Small delay
        step.end([1, 2])

        assert step._duration_ms >= 10

    def test_step_end_sends_event(self, mock_run, mock_transport) -> None:
        step = Step(mock_run, mock_transport, "test", StepType.filter, [1, 2, 3], 0)
        step.end([1, 2])

        assert mock_transport.send.call_count == 2
        end_event = mock_transport.send.call_args_list[1][0][0]
        assert end_event["event_type"] == "step_end"
        assert end_event["output_count"] == 2
        assert end_event["status"] == "success"

    def test_step_end_is_idempotent(self, mock_run, mock_transport) -> None:
        step = Step(mock_run, mock_transport, "test", StepType.filter, [], 0)
        step.end([])
        step.end([])  # Second call should be ignored

        assert mock_transport.send.call_count == 2  # Only start + one end

    def test_step_end_with_error(self, mock_run, mock_transport) -> None:
        step = Step(mock_run, mock_transport, "test", StepType.filter, [], 0)
        step.end_with_error(ValueError("something failed"))

        end_event = mock_transport.send.call_args_list[1][0][0]
        assert end_event["status"] == "error"
        assert "ValueError" in end_event["error_message"]
        assert "something failed" in end_event["error_message"]

    def test_step_end_with_error_string(self, mock_run, mock_transport) -> None:
        step = Step(mock_run, mock_transport, "test", StepType.filter, [], 0)
        step.end_with_error("custom error message")

        end_event = mock_transport.send.call_args_list[1][0][0]
        assert end_event["error_message"] == "custom error message"

    def test_step_attach_reasoning_dict(self, mock_run, mock_transport) -> None:
        step = Step(mock_run, mock_transport, "test", StepType.filter, [], 0)
        step.attach_reasoning({"score_threshold": 0.5, "method": "cosine"})
        step.end([])

        end_event = mock_transport.send.call_args_list[1][0][0]
        assert end_event["reasoning"]["score_threshold"] == 0.5
        assert end_event["reasoning"]["method"] == "cosine"

    def test_step_attach_reasoning_string(self, mock_run, mock_transport) -> None:
        step = Step(mock_run, mock_transport, "test", StepType.filter, [], 0)
        step.attach_reasoning("Filtered items below threshold")
        step.end([])

        end_event = mock_transport.send.call_args_list[1][0][0]
        assert end_event["reasoning"]["explanation"] == "Filtered items below threshold"

    def test_step_with_metadata(self, mock_run, mock_transport) -> None:
        step = Step(
            mock_run,
            mock_transport,
            "test",
            StepType.filter,
            [],
            0,
            metadata={"custom_key": "custom_value"},
        )

        start_event = mock_transport.send.call_args[0][0]
        assert start_event["metadata"]["custom_key"] == "custom_value"

    def test_step_type_from_string(self, mock_run, mock_transport) -> None:
        step = Step(mock_run, mock_transport, "test", "llm", [], 0)
        assert step.step_type == StepType.llm

    def test_step_input_with_candidates(self, mock_run, mock_transport) -> None:
        candidates = [{"id": "1", "score": 0.9}, {"id": "2", "score": 0.8}]
        Step(mock_run, mock_transport, "test", StepType.filter, candidates, 0)

        start_event = mock_transport.send.call_args[0][0]
        assert start_event["input_count"] == 2
        assert start_event["input_summary"]["_type"] == "candidates"
        assert len(start_event["input_summary"]["_candidates"]) == 2
