"""Tests for SDK Step class and payload helpers."""

import time
from unittest.mock import Mock

import pytest

from sdk.step import (
    LARGE_LIST_THRESHOLD,
    LARGE_STRING_THRESHOLD,
    MAX_STRING_LENGTH,
    PREVIEW_SIZE,
    STRING_PREVIEW_SIZE,
    PayloadCollector,
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
        """Small non-candidate lists now store ALL values inline."""
        items = [1, 2, 3, 4, 5]
        result = summarize_payload(items)
        assert result["_type"] == "list"
        assert result["_count"] == 5
        assert result["_item_type"] == "int"
        assert "_candidates" not in result
        # New: small lists store all values inline
        assert result["_values"] == [1, 2, 3, 4, 5]

    def test_dict_captures_keys(self) -> None:
        data = {"query": "laptop", "user_id": "u-123", "filters": {"price": 1000}}
        result = summarize_payload(data)
        assert result["_type"] == "dict"
        assert result["_key_count"] == 3
        assert set(result["_keys"]) == {"query", "user_id", "filters"}

    def test_dict_captures_scalar_values(self) -> None:
        data = {"name": "test", "count": 5, "active": True}
        result = summarize_payload(data)
        # Numbers and bools are stored directly
        assert result["_values"]["count"] == 5
        assert result["_values"]["active"] is True
        # Strings are now recursively summarized for consistency
        assert result["_values"]["name"]["_type"] == "str"
        assert result["_values"]["name"]["_value"] == "test"

    def test_nested_dict_recursive(self) -> None:
        """Nested dicts are now recursively summarized for full detail capture."""
        data = {"config": {"nested": "value"}}
        result = summarize_payload(data)
        # Nested dict is fully summarized, not just {"_type": "dict"}
        assert result["_values"]["config"]["_type"] == "dict"
        assert result["_values"]["config"]["_keys"] == ["nested"]
        assert result["_values"]["config"]["_values"]["nested"]["_value"] == "value"

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


class TestPayloadCollector:
    """Tests for PayloadCollector class."""

    def test_generates_sequential_refs(self) -> None:
        """PayloadCollector generates sequential reference IDs."""
        collector = PayloadCollector()
        ref1 = collector.add("data1")
        ref2 = collector.add("data2")
        ref3 = collector.add("data3")

        assert ref1 == "p-000"
        assert ref2 == "p-001"
        assert ref3 == "p-002"

    def test_stores_data_by_ref(self) -> None:
        """PayloadCollector stores data retrievable by ref."""
        collector = PayloadCollector()
        data = [1, 2, 3, 4, 5]
        ref_id = collector.add(data)

        payloads = collector.get_payloads()
        assert payloads[ref_id] == data

    def test_get_payloads_returns_none_when_empty(self) -> None:
        """get_payloads returns None when no data added."""
        collector = PayloadCollector()
        assert collector.get_payloads() is None

    def test_get_payloads_returns_dict_when_has_data(self) -> None:
        """get_payloads returns dict when data exists."""
        collector = PayloadCollector()
        collector.add("some data")
        payloads = collector.get_payloads()
        assert isinstance(payloads, dict)
        assert len(payloads) == 1


class TestPayloadExternalization:
    """Tests for payload externalization behavior."""

    def test_small_list_stores_all_values_inline(self) -> None:
        """Small lists store ALL values inline."""
        collector = PayloadCollector()
        items = [1, 2, 3, 4, 5]  # Small list
        result = summarize_payload(items, collector=collector)

        assert result["_type"] == "list"
        assert result["_count"] == 5
        assert result["_values"] == [1, 2, 3, 4, 5]
        assert "_ref" not in result
        assert collector.get_payloads() is None  # Nothing externalized

    def test_large_list_externalized_with_preview(self) -> None:
        """Large lists are externalized with reference + preview."""
        collector = PayloadCollector()
        # Create a list larger than LARGE_LIST_THRESHOLD
        large_list = list(range(LARGE_LIST_THRESHOLD + 50))
        result = summarize_payload(large_list, collector=collector)

        assert result["_type"] == "list"
        assert result["_count"] == LARGE_LIST_THRESHOLD + 50
        assert "_ref" in result  # Has reference
        assert result["_preview"] == list(range(PREVIEW_SIZE))  # First 5 items

        # Data is externalized
        payloads = collector.get_payloads()
        assert payloads is not None
        assert result["_ref"] in payloads
        assert payloads[result["_ref"]] == large_list

    def test_large_string_externalized_with_preview(self) -> None:
        """Large strings are externalized with reference + preview."""
        collector = PayloadCollector()
        # Create a string larger than LARGE_STRING_THRESHOLD
        large_string = "x" * (LARGE_STRING_THRESHOLD + 100)
        result = summarize_payload(large_string, collector=collector)

        assert result["_type"] == "str"
        assert result["_length"] == LARGE_STRING_THRESHOLD + 100
        assert "_ref" in result  # Has reference
        assert result["_preview"] == "x" * STRING_PREVIEW_SIZE  # First 100 chars

        # Data is externalized
        payloads = collector.get_payloads()
        assert payloads is not None
        assert result["_ref"] in payloads
        assert payloads[result["_ref"]] == large_string

    def test_small_string_stored_inline(self) -> None:
        """Small strings are stored inline, not externalized."""
        collector = PayloadCollector()
        small_string = "hello world"
        result = summarize_payload(small_string, collector=collector)

        assert result["_type"] == "str"
        assert result["_value"] == "hello world"
        assert "_ref" not in result
        assert collector.get_payloads() is None

    def test_nested_dict_with_large_list(self) -> None:
        """Large lists inside dicts are externalized."""
        collector = PayloadCollector()
        data = {
            "embedding": list(range(LARGE_LIST_THRESHOLD + 10)),
            "name": "test",
        }
        result = summarize_payload(data, collector=collector)

        # The embedding should be externalized
        embedding_summary = result["_values"]["embedding"]
        assert embedding_summary["_type"] == "list"
        assert "_ref" in embedding_summary

        # Payloads should contain the full list
        payloads = collector.get_payloads()
        assert payloads is not None

    def test_without_collector_no_externalization(self) -> None:
        """Without collector, large data is not externalized."""
        large_list = list(range(LARGE_LIST_THRESHOLD + 50))
        result = summarize_payload(large_list)  # No collector

        assert result["_type"] == "list"
        assert "_ref" not in result  # No reference without collector
        assert "_values" in result  # Values stored inline


class TestStepPayloads:
    """Tests for Step class with _payloads."""

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

    def test_step_start_event_includes_payloads(self, mock_run, mock_transport) -> None:
        """Step start event includes _payloads field."""
        Step(mock_run, mock_transport, "test", StepType.filter, [1, 2, 3], 0)

        start_event = mock_transport.send.call_args[0][0]
        assert "_payloads" in start_event
        # Small input, no externalization
        assert start_event["_payloads"] is None

    def test_step_start_with_large_input_has_payloads(self, mock_run, mock_transport) -> None:
        """Step start event with large input has _payloads."""
        large_input = list(range(LARGE_LIST_THRESHOLD + 10))
        Step(mock_run, mock_transport, "test", StepType.filter, large_input, 0)

        start_event = mock_transport.send.call_args[0][0]
        assert start_event["_payloads"] is not None
        assert "p-000" in start_event["_payloads"]

    def test_step_end_event_includes_payloads(self, mock_run, mock_transport) -> None:
        """Step end event includes _payloads field."""
        step = Step(mock_run, mock_transport, "test", StepType.filter, [], 0)
        step.end([1, 2, 3])

        end_event = mock_transport.send.call_args_list[1][0][0]
        assert "_payloads" in end_event

    def test_step_end_with_large_output_has_payloads(self, mock_run, mock_transport) -> None:
        """Step end event with large output has _payloads."""
        step = Step(mock_run, mock_transport, "test", StepType.filter, [], 0)
        large_output = list(range(LARGE_LIST_THRESHOLD + 10))
        step.end(large_output)

        end_event = mock_transport.send.call_args_list[1][0][0]
        assert end_event["_payloads"] is not None
