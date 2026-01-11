"""Tests for SDK decorators and helpers."""

import asyncio
from unittest.mock import Mock

import pytest

from sdk import (
    XRayClient,
    attach_candidates,
    attach_reasoning,
    current_run,
    current_step,
    instrument_class,
    step,
)
from sdk.config import XRayConfig
from shared.types import StepStatus, StepType


class TestStepDecoratorSync:
    """Tests for @step decorator with synchronous functions."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Create mock transport."""
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def client(self, mock_transport: Mock) -> XRayClient:
        """Create a started client with mock transport."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client._transport = mock_transport
        client._started = True
        yield client
        client._started = False

    def test_decorated_sync_function_creates_step(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Decorated sync function creates step when run is active."""

        @step(step_type="filter")
        def filter_items(items: list[dict]) -> list[dict]:
            return [i for i in items if i["score"] > 0.5]

        candidates = [{"id": "1", "score": 0.8}, {"id": "2", "score": 0.3}]

        with client.start_run("test_pipeline") as run:
            result = filter_items(candidates)

        assert result == [{"id": "1", "score": 0.8}]
        # Should have: run_start, step_start, step_end, run_end
        assert mock_transport.send.call_count == 4

        # Check step_start event
        step_start = mock_transport.send.call_args_list[1][0][0]
        assert step_start["event_type"] == "step_start"
        assert step_start["step_name"] == "filter_items"
        assert step_start["step_type"] == "filter"

        # Check step_end event
        step_end = mock_transport.send.call_args_list[2][0][0]
        assert step_end["event_type"] == "step_end"
        assert step_end["status"] == "success"

    def test_decorated_sync_without_run_works(self) -> None:
        """Decorated sync function works without active run."""

        @step(step_type="filter")
        def filter_items(items: list[dict]) -> list[dict]:
            return [i for i in items if i["score"] > 0.5]

        candidates = [{"id": "1", "score": 0.8}, {"id": "2", "score": 0.3}]

        # No run active - should work normally
        result = filter_items(candidates)
        assert result == [{"id": "1", "score": 0.8}]

    def test_decorated_sync_captures_input_output(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Decorated sync function captures first arg as input and return as output."""

        @step(step_type="transform")
        def double_values(items: list[int]) -> list[int]:
            return [i * 2 for i in items]

        with client.start_run("test_pipeline"):
            result = double_values([1, 2, 3])

        assert result == [2, 4, 6]

        # Check step_start has input
        step_start = mock_transport.send.call_args_list[1][0][0]
        assert step_start["input_summary"] is not None
        assert step_start["input_count"] == 3

        # Check step_end has output
        step_end = mock_transport.send.call_args_list[2][0][0]
        assert step_end["output_summary"] is not None
        assert step_end["output_count"] == 3

    def test_decorated_sync_exception_marks_error(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Decorated sync function marks step as error on exception."""

        @step(step_type="transform")
        def failing_transform(items: list[int]) -> list[int]:
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            with client.start_run("test_pipeline"):
                failing_transform([1, 2, 3])

        # Check step_end has error status
        step_end = mock_transport.send.call_args_list[2][0][0]
        assert step_end["event_type"] == "step_end"
        assert step_end["status"] == "error"
        assert "ValueError" in step_end["error_message"]

    def test_decorated_sync_exception_propagates(
        self, client: XRayClient
    ) -> None:
        """Decorated sync function propagates exceptions."""

        @step(step_type="transform")
        def failing_transform(items: list[int]) -> list[int]:
            raise RuntimeError("Should propagate")

        with pytest.raises(RuntimeError, match="Should propagate"):
            with client.start_run("test_pipeline"):
                failing_transform([1, 2, 3])

    def test_step_name_defaults_to_function_name(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Step name defaults to function name."""

        @step()
        def my_custom_function(x: int) -> int:
            return x + 1

        with client.start_run("test_pipeline"):
            my_custom_function(5)

        step_start = mock_transport.send.call_args_list[1][0][0]
        assert step_start["step_name"] == "my_custom_function"

    def test_step_name_can_be_customized(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Step name can be customized via parameter."""

        @step(name="custom_step_name")
        def my_function(x: int) -> int:
            return x + 1

        with client.start_run("test_pipeline"):
            my_function(5)

        step_start = mock_transport.send.call_args_list[1][0][0]
        assert step_start["step_name"] == "custom_step_name"

    def test_step_type_is_set_correctly(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Step type is set correctly from decorator parameter."""

        @step(step_type=StepType.llm)
        def call_llm(prompt: str) -> str:
            return "response"

        with client.start_run("test_pipeline"):
            call_llm("test prompt")

        step_start = mock_transport.send.call_args_list[1][0][0]
        assert step_start["step_type"] == "llm"

    def test_step_type_accepts_string(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Step type accepts string value."""

        @step(step_type="rank")
        def rank_items(items: list[dict]) -> list[dict]:
            return sorted(items, key=lambda x: x["score"], reverse=True)

        with client.start_run("test_pipeline"):
            rank_items([{"id": "1", "score": 0.5}])

        step_start = mock_transport.send.call_args_list[1][0][0]
        assert step_start["step_type"] == "rank"

    def test_functools_wraps_preserves_metadata(self) -> None:
        """functools.wraps preserves function metadata."""

        @step(step_type="filter")
        def filter_candidates(items: list[dict]) -> list[dict]:
            """Filter candidates by score threshold."""
            return [i for i in items if i["score"] > 0.5]

        assert filter_candidates.__name__ == "filter_candidates"
        assert filter_candidates.__doc__ == "Filter candidates by score threshold."

    def test_decorated_function_without_args(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Decorated function works with no arguments."""

        @step(step_type="other")
        def no_args_function() -> str:
            return "result"

        with client.start_run("test_pipeline"):
            result = no_args_function()

        assert result == "result"

        # When no args, input_data is None which gets summarized
        step_start = mock_transport.send.call_args_list[1][0][0]
        assert step_start["input_summary"]["_type"] == "null"
        assert step_start["input_summary"]["_value"] is None


class TestStepDecoratorAsync:
    """Tests for @step decorator with async functions."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Create mock transport."""
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def client(self, mock_transport: Mock) -> XRayClient:
        """Create a started client with mock transport."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client._transport = mock_transport
        client._started = True
        yield client
        client._started = False

    @pytest.mark.asyncio
    async def test_decorated_async_function_creates_step(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Decorated async function creates step when run is active."""

        @step(step_type="llm")
        async def call_llm(prompt: str) -> str:
            await asyncio.sleep(0.01)
            return "response"

        with client.start_run("test_pipeline"):
            result = await call_llm("test prompt")

        assert result == "response"
        # Should have: run_start, step_start, step_end, run_end
        assert mock_transport.send.call_count == 4

        step_start = mock_transport.send.call_args_list[1][0][0]
        assert step_start["event_type"] == "step_start"
        assert step_start["step_name"] == "call_llm"
        assert step_start["step_type"] == "llm"

    @pytest.mark.asyncio
    async def test_decorated_async_without_run_works(self) -> None:
        """Decorated async function works without active run."""

        @step(step_type="llm")
        async def call_llm(prompt: str) -> str:
            await asyncio.sleep(0.01)
            return "response"

        # No run active - should work normally
        result = await call_llm("test prompt")
        assert result == "response"

    @pytest.mark.asyncio
    async def test_decorated_async_exception_marks_error(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Decorated async function marks step as error on exception."""

        @step(step_type="llm")
        async def failing_llm(prompt: str) -> str:
            await asyncio.sleep(0.01)
            raise ValueError("LLM error")

        with pytest.raises(ValueError, match="LLM error"):
            with client.start_run("test_pipeline"):
                await failing_llm("test prompt")

        step_end = mock_transport.send.call_args_list[2][0][0]
        assert step_end["status"] == "error"
        assert "ValueError" in step_end["error_message"]

    @pytest.mark.asyncio
    async def test_decorated_async_exception_propagates(
        self, client: XRayClient
    ) -> None:
        """Decorated async function propagates exceptions."""

        @step(step_type="llm")
        async def failing_llm(prompt: str) -> str:
            raise RuntimeError("Should propagate")

        with pytest.raises(RuntimeError, match="Should propagate"):
            with client.start_run("test_pipeline"):
                await failing_llm("test prompt")

    @pytest.mark.asyncio
    async def test_async_step_preserves_metadata(self) -> None:
        """Async decorated function preserves metadata."""

        @step(step_type="llm")
        async def async_function(x: int) -> int:
            """Async docstring."""
            return x

        assert async_function.__name__ == "async_function"
        assert async_function.__doc__ == "Async docstring."


class TestInstrumentClass:
    """Tests for @instrument_class decorator."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Create mock transport."""
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def client(self, mock_transport: Mock) -> XRayClient:
        """Create a started client with mock transport."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client._transport = mock_transport
        client._started = True
        yield client
        client._started = False

    def test_instruments_all_public_methods(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """instrument_class decorates all public methods."""

        @instrument_class(step_type="filter")
        class FilterPipeline:
            def filter_by_price(self, items: list[dict]) -> list[dict]:
                return [i for i in items if i["price"] < 100]

            def filter_by_rating(self, items: list[dict]) -> list[dict]:
                return [i for i in items if i["rating"] > 4.0]

        pipeline = FilterPipeline()
        items = [{"id": "1", "price": 50, "rating": 4.5}]

        with client.start_run("test_pipeline"):
            pipeline.filter_by_price(items)
            pipeline.filter_by_rating(items)

        # run_start + 2*(step_start + step_end) + run_end = 6
        assert mock_transport.send.call_count == 6

        # Check step names
        step1_start = mock_transport.send.call_args_list[1][0][0]
        assert step1_start["step_name"] == "filter_by_price"

        step2_start = mock_transport.send.call_args_list[3][0][0]
        assert step2_start["step_name"] == "filter_by_rating"

    def test_skips_private_methods(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """instrument_class skips private methods (starting with _)."""

        @instrument_class(step_type="transform")
        class MyClass:
            def public_method(self, x: int) -> int:
                return self._helper(x)

            def _helper(self, x: int) -> int:
                return x * 2

        obj = MyClass()

        with client.start_run("test_pipeline"):
            result = obj.public_method(5)

        assert result == 10
        # Only public_method should be instrumented
        # run_start + step_start + step_end + run_end = 4
        assert mock_transport.send.call_count == 4

    def test_skips_dunder_methods(self) -> None:
        """instrument_class skips dunder methods."""

        @instrument_class()
        class MyClass:
            def __init__(self) -> None:
                self.value = 0

            def increment(self) -> int:
                self.value += 1
                return self.value

        # Should not raise and __init__ should work
        obj = MyClass()
        assert obj.value == 0

    def test_exclude_option_works(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """exclude option prevents specified methods from being instrumented."""

        @instrument_class(step_type="transform", exclude=("helper",))
        class MyClass:
            def process(self, x: int) -> int:
                return self.helper(x)

            def helper(self, x: int) -> int:
                return x * 2

        obj = MyClass()

        with client.start_run("test_pipeline"):
            result = obj.process(5)

        assert result == 10
        # Only process should be instrumented
        # run_start + step_start + step_end + run_end = 4
        assert mock_transport.send.call_count == 4

        step_start = mock_transport.send.call_args_list[1][0][0]
        assert step_start["step_name"] == "process"

    def test_step_type_applied_to_all_methods(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """step_type is applied to all instrumented methods."""

        @instrument_class(step_type="llm")
        class LLMPipeline:
            def call_model_a(self, prompt: str) -> str:
                return "response_a"

            def call_model_b(self, prompt: str) -> str:
                return "response_b"

        pipeline = LLMPipeline()

        with client.start_run("test_pipeline"):
            pipeline.call_model_a("prompt")
            pipeline.call_model_b("prompt")

        step1_start = mock_transport.send.call_args_list[1][0][0]
        assert step1_start["step_type"] == "llm"

        step2_start = mock_transport.send.call_args_list[3][0][0]
        assert step2_start["step_type"] == "llm"

    def test_works_without_parentheses(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """instrument_class works without parentheses."""

        @instrument_class
        class SimpleClass:
            def method(self, x: int) -> int:
                return x + 1

        obj = SimpleClass()

        with client.start_run("test_pipeline"):
            result = obj.method(5)

        assert result == 6
        assert mock_transport.send.call_count == 4

    def test_works_with_empty_parentheses(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """instrument_class works with empty parentheses."""

        @instrument_class()
        class SimpleClass:
            def method(self, x: int) -> int:
                return x + 1

        obj = SimpleClass()

        with client.start_run("test_pipeline"):
            result = obj.method(5)

        assert result == 6
        assert mock_transport.send.call_count == 4


class TestAttachReasoning:
    """Tests for attach_reasoning helper."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Create mock transport."""
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def client(self, mock_transport: Mock) -> XRayClient:
        """Create a started client with mock transport."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client._transport = mock_transport
        client._started = True
        yield client
        client._started = False

    def test_attach_reasoning_with_dict(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """attach_reasoning works with dict."""

        @step(step_type="filter")
        def filter_items(items: list[dict]) -> list[dict]:
            filtered = [i for i in items if i["score"] > 0.5]
            attach_reasoning({"threshold": 0.5, "removed": len(items) - len(filtered)})
            return filtered

        with client.start_run("test_pipeline"):
            filter_items([{"id": "1", "score": 0.8}, {"id": "2", "score": 0.3}])

        step_end = mock_transport.send.call_args_list[2][0][0]
        assert step_end["reasoning"] is not None
        assert step_end["reasoning"]["threshold"] == 0.5
        assert step_end["reasoning"]["removed"] == 1

    def test_attach_reasoning_with_string(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """attach_reasoning works with string."""

        @step(step_type="filter")
        def filter_items(items: list[dict]) -> list[dict]:
            attach_reasoning("Filtered items based on score threshold")
            return items

        with client.start_run("test_pipeline"):
            filter_items([{"id": "1", "score": 0.8}])

        step_end = mock_transport.send.call_args_list[2][0][0]
        assert step_end["reasoning"]["explanation"] == "Filtered items based on score threshold"

    def test_attach_reasoning_returns_false_no_step(self) -> None:
        """attach_reasoning returns False when no active step."""
        result = attach_reasoning({"key": "value"})
        assert result is False

    def test_attach_reasoning_returns_true_with_step(
        self, client: XRayClient
    ) -> None:
        """attach_reasoning returns True when step is active."""

        @step(step_type="filter")
        def filter_items(items: list[dict]) -> list[dict]:
            result = attach_reasoning({"threshold": 0.5})
            assert result is True
            return items

        with client.start_run("test_pipeline"):
            filter_items([{"id": "1", "score": 0.8}])

    def test_attach_reasoning_accumulates(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Multiple attach_reasoning calls accumulate."""

        @step(step_type="filter")
        def filter_items(items: list[dict]) -> list[dict]:
            attach_reasoning({"threshold": 0.5})
            attach_reasoning({"strategy": "score_based"})
            return items

        with client.start_run("test_pipeline"):
            filter_items([{"id": "1", "score": 0.8}])

        step_end = mock_transport.send.call_args_list[2][0][0]
        assert step_end["reasoning"]["threshold"] == 0.5
        assert step_end["reasoning"]["strategy"] == "score_based"


class TestAttachCandidates:
    """Tests for attach_candidates helper."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Create mock transport."""
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def client(self, mock_transport: Mock) -> XRayClient:
        """Create a started client with mock transport."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client._transport = mock_transport
        client._started = True
        yield client
        client._started = False

    def test_attach_candidates_extracts_ids(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """attach_candidates extracts id field."""

        @step(step_type="rank")
        def rank_items(items: list[dict]) -> list[dict]:
            ranked = sorted(items, key=lambda x: x["score"], reverse=True)
            attach_candidates(ranked, phase="output")
            return ranked

        candidates = [
            {"id": "1", "score": 0.8},
            {"id": "2", "score": 0.9},
        ]

        with client.start_run("test_pipeline"):
            rank_items(candidates)

        step_end = mock_transport.send.call_args_list[2][0][0]
        output_candidates = step_end["reasoning"]["output_candidates"]
        assert len(output_candidates) == 2
        assert output_candidates[0]["id"] == "2"  # Sorted by score
        assert output_candidates[1]["id"] == "1"

    def test_attach_candidates_includes_scores(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """attach_candidates includes score field."""

        @step(step_type="rank")
        def rank_items(items: list[dict]) -> list[dict]:
            attach_candidates(items, phase="input")
            return items

        candidates = [{"id": "1", "score": 0.8}]

        with client.start_run("test_pipeline"):
            rank_items(candidates)

        step_end = mock_transport.send.call_args_list[2][0][0]
        input_candidates = step_end["reasoning"]["input_candidates"]
        assert input_candidates[0]["score"] == 0.8

    def test_attach_candidates_includes_reason(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """attach_candidates includes reason field."""

        @step(step_type="filter")
        def filter_items(items: list[dict]) -> list[dict]:
            attach_candidates(items, phase="output")
            return items

        candidates = [{"id": "1", "score": 0.8, "reason": "passed threshold"}]

        with client.start_run("test_pipeline"):
            filter_items(candidates)

        step_end = mock_transport.send.call_args_list[2][0][0]
        output_candidates = step_end["reasoning"]["output_candidates"]
        assert output_candidates[0]["reason"] == "passed threshold"

    def test_attach_candidates_returns_false_no_step(self) -> None:
        """attach_candidates returns False when no active step."""
        result = attach_candidates([{"id": "1"}], phase="output")
        assert result is False

    def test_attach_candidates_supports_alternate_id_fields(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """attach_candidates supports _id and candidate_id fields."""

        @step(step_type="filter")
        def process_items(items: list[dict]) -> list[dict]:
            attach_candidates(items, phase="output")
            return items

        # Test _id
        with client.start_run("test_pipeline"):
            process_items([{"_id": "mongo_id", "score": 0.5}])

        step_end = mock_transport.send.call_args_list[2][0][0]
        assert step_end["reasoning"]["output_candidates"][0]["id"] == "mongo_id"

    def test_attach_candidates_phase_parameter(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """attach_candidates uses phase parameter for key name."""

        @step(step_type="transform")
        def transform_items(items: list[dict]) -> list[dict]:
            attach_candidates(items, phase="input")
            attach_candidates(items, phase="output")
            return items

        with client.start_run("test_pipeline"):
            transform_items([{"id": "1"}])

        step_end = mock_transport.send.call_args_list[2][0][0]
        assert "input_candidates" in step_end["reasoning"]
        assert "output_candidates" in step_end["reasoning"]


class TestDecoratorIntegration:
    """Integration tests for decorators working together."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Create mock transport."""
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def client(self, mock_transport: Mock) -> XRayClient:
        """Create a started client with mock transport."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client._transport = mock_transport
        client._started = True
        yield client
        client._started = False

    def test_full_pipeline_with_decorators(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Full pipeline flow with decorators and helpers."""

        @step(step_type="filter")
        def filter_candidates(candidates: list[dict]) -> list[dict]:
            filtered = [c for c in candidates if c["score"] > 0.5]
            attach_reasoning({"threshold": 0.5, "filtered_count": len(filtered)})
            attach_candidates(filtered, phase="output")
            return filtered

        @step(step_type="rank")
        def rank_candidates(candidates: list[dict]) -> list[dict]:
            ranked = sorted(candidates, key=lambda x: x["score"], reverse=True)
            attach_reasoning("Ranked by score descending")
            return ranked

        candidates = [
            {"id": "1", "score": 0.9},
            {"id": "2", "score": 0.3},
            {"id": "3", "score": 0.7},
        ]

        with client.start_run("recommendation_pipeline") as run:
            filtered = filter_candidates(candidates)
            ranked = rank_candidates(filtered)

        assert len(ranked) == 2
        assert ranked[0]["id"] == "1"  # Highest score first

        # run_start + filter_start + filter_end + rank_start + rank_end + run_end = 6
        assert mock_transport.send.call_count == 6

    def test_nested_steps_work_correctly(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Nested decorated functions create proper step sequence."""

        @step(step_type="transform")
        def outer(x: int) -> int:
            return inner(x) + 1

        @step(step_type="transform")
        def inner(x: int) -> int:
            return x * 2

        with client.start_run("test_pipeline"):
            result = outer(5)

        assert result == 11  # (5 * 2) + 1

        # run_start + outer_start + inner_start + inner_end + outer_end + run_end = 6
        assert mock_transport.send.call_count == 6

    @pytest.mark.asyncio
    async def test_mixed_sync_async_pipeline(
        self, client: XRayClient, mock_transport: Mock
    ) -> None:
        """Pipeline with both sync and async decorated functions."""

        @step(step_type="filter")
        def sync_filter(items: list[dict]) -> list[dict]:
            return [i for i in items if i["score"] > 0.5]

        @step(step_type="llm")
        async def async_enrich(items: list[dict]) -> list[dict]:
            await asyncio.sleep(0.01)
            return [{**i, "enriched": True} for i in items]

        candidates = [{"id": "1", "score": 0.8}]

        with client.start_run("test_pipeline"):
            filtered = sync_filter(candidates)
            enriched = await async_enrich(filtered)

        assert enriched == [{"id": "1", "score": 0.8, "enriched": True}]
        # run_start + filter_start + filter_end + enrich_start + enrich_end + run_end = 6
        assert mock_transport.send.call_count == 6
