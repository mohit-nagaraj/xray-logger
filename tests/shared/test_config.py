"""Tests for shared configuration utilities."""

from pathlib import Path

import pytest

from shared.config import (
    CONFIG_FILENAME,
    find_config_file,
    get_section,
    load_yaml_file,
)


class TestConfigFilename:
    """Tests for config filename constant."""

    def test_config_filename(self) -> None:
        """Config filename is xray.config.yaml."""
        assert CONFIG_FILENAME == "xray.config.yaml"


class TestFindConfigFile:
    """Tests for find_config_file function."""

    def test_finds_config_in_current_dir(self, tmp_path: Path) -> None:
        """Finds config file in current directory."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text("sdk:\n  base_url: http://test")

        result = find_config_file(tmp_path)
        assert result == config_file

    def test_finds_config_in_parent_dir(self, tmp_path: Path) -> None:
        """Finds config file in parent directory."""
        # Create config in parent
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text("sdk:\n  base_url: http://test")

        # Search from child directory
        child_dir = tmp_path / "subdir" / "deep"
        child_dir.mkdir(parents=True)

        result = find_config_file(child_dir)
        assert result == config_file

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """Returns None when no config file found."""
        result = find_config_file(tmp_path)
        assert result is None


class TestLoadYamlFile:
    """Tests for load_yaml_file function."""

    def test_loads_valid_yaml(self, tmp_path: Path) -> None:
        """Loads valid YAML content."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            """
sdk:
  base_url: http://localhost:8000
  buffer_size: 2000
api:
  database_url: postgresql://localhost/xray
"""
        )

        result = load_yaml_file(config_file)
        assert result["sdk"]["base_url"] == "http://localhost:8000"
        assert result["sdk"]["buffer_size"] == 2000
        assert result["api"]["database_url"] == "postgresql://localhost/xray"

    def test_returns_empty_dict_for_nonexistent_file(self) -> None:
        """Returns empty dict for nonexistent file."""
        result = load_yaml_file("/nonexistent/path.yaml")
        assert result == {}

    def test_returns_empty_dict_for_empty_file(self, tmp_path: Path) -> None:
        """Returns empty dict for empty file."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        result = load_yaml_file(config_file)
        assert result == {}


class TestGetSection:
    """Tests for get_section function."""

    def test_extracts_sdk_section(self) -> None:
        """Extracts sdk section from config."""
        config = {
            "sdk": {"base_url": "http://test", "buffer_size": 500},
            "api": {"database_url": "postgres://"},
        }

        result = get_section(config, "sdk")
        assert result == {"base_url": "http://test", "buffer_size": 500}

    def test_extracts_api_section(self) -> None:
        """Extracts api section from config."""
        config = {
            "sdk": {"base_url": "http://test"},
            "api": {"database_url": "postgres://", "debug": True},
        }

        result = get_section(config, "api")
        assert result == {"database_url": "postgres://", "debug": True}

    def test_returns_empty_dict_for_missing_section(self) -> None:
        """Returns empty dict when section doesn't exist."""
        config = {"sdk": {"base_url": "http://test"}}

        result = get_section(config, "api")
        assert result == {}

    def test_returns_empty_dict_for_non_dict_section(self) -> None:
        """Returns empty dict when section is not a dict."""
        config = {"sdk": "not a dict"}

        result = get_section(config, "sdk")
        assert result == {}
