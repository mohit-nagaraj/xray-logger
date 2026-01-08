"""Tests for shared type definitions."""

import json

import pytest

from shared.types import DetailLevel, RunStatus, StepStatus, StepType


class TestStepType:
    """Tests for StepType enum."""

    def test_all_values_exist(self) -> None:
        """Verify all expected step types are defined."""
        expected = {"filter", "rank", "llm", "retrieval", "transform", "other"}
        actual = {e.value for e in StepType}
        assert actual == expected

    def test_instantiation_from_string(self) -> None:
        """Enum can be created from string value."""
        assert StepType("filter") == StepType.filter
        assert StepType("llm") == StepType.llm

    def test_invalid_value_raises(self) -> None:
        """Invalid value raises ValueError."""
        with pytest.raises(ValueError):
            StepType("invalid")

    def test_json_serialization(self) -> None:
        """Enum serializes to JSON as string."""
        assert json.dumps(StepType.filter) == '"filter"'
        assert json.dumps(StepType.rank) == '"rank"'

    def test_json_in_dict(self) -> None:
        """Enum works in dict serialization."""
        data = {"type": StepType.llm, "name": "test"}
        result = json.dumps(data)
        assert '"type": "llm"' in result

    def test_string_comparison(self) -> None:
        """Enum can be compared to string."""
        assert StepType.filter == "filter"
        assert StepType.rank == "rank"


class TestRunStatus:
    """Tests for RunStatus enum."""

    def test_all_values_exist(self) -> None:
        """Verify all expected run statuses are defined."""
        expected = {"running", "success", "error"}
        actual = {e.value for e in RunStatus}
        assert actual == expected

    def test_instantiation_from_string(self) -> None:
        """Enum can be created from string value."""
        assert RunStatus("running") == RunStatus.running
        assert RunStatus("success") == RunStatus.success
        assert RunStatus("error") == RunStatus.error

    def test_json_serialization(self) -> None:
        """Enum serializes to JSON as string."""
        assert json.dumps(RunStatus.running) == '"running"'
        assert json.dumps(RunStatus.success) == '"success"'
        assert json.dumps(RunStatus.error) == '"error"'


class TestStepStatus:
    """Tests for StepStatus enum."""

    def test_all_values_exist(self) -> None:
        """Verify all expected step statuses are defined."""
        expected = {"running", "success", "error"}
        actual = {e.value for e in StepStatus}
        assert actual == expected

    def test_instantiation_from_string(self) -> None:
        """Enum can be created from string value."""
        assert StepStatus("running") == StepStatus.running
        assert StepStatus("success") == StepStatus.success

    def test_json_serialization(self) -> None:
        """Enum serializes to JSON as string."""
        assert json.dumps(StepStatus.error) == '"error"'


class TestDetailLevel:
    """Tests for DetailLevel enum."""

    def test_all_values_exist(self) -> None:
        """Verify all expected detail levels are defined."""
        expected = {"summary", "full"}
        actual = {e.value for e in DetailLevel}
        assert actual == expected

    def test_instantiation_from_string(self) -> None:
        """Enum can be created from string value."""
        assert DetailLevel("summary") == DetailLevel.summary
        assert DetailLevel("full") == DetailLevel.full

    def test_json_serialization(self) -> None:
        """Enum serializes to JSON as string."""
        assert json.dumps(DetailLevel.summary) == '"summary"'
        assert json.dumps(DetailLevel.full) == '"full"'

    def test_default_is_summary(self) -> None:
        """Summary is the expected default detail level."""
        # This documents the expected default behavior
        assert DetailLevel.summary.value == "summary"


class TestEnumInteroperability:
    """Tests for enum interoperability between modules."""

    def test_enums_importable_from_shared(self) -> None:
        """All enums can be imported from shared package."""
        from shared import DetailLevel, RunStatus, StepStatus, StepType

        assert StepType.filter == "filter"
        assert RunStatus.running == "running"
        assert StepStatus.success == "success"
        assert DetailLevel.full == "full"

    def test_all_exports_defined(self) -> None:
        """__all__ exports all expected types."""
        from shared import __all__

        expected = {"StepType", "RunStatus", "StepStatus", "DetailLevel"}
        assert set(__all__) == expected
