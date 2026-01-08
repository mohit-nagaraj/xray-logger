"""Tests for SDK configuration."""

import tempfile
from pathlib import Path

import pytest

from sdk.config import XRayConfig, load_config
from shared.config import CONFIG_FILENAME
from shared.types import DetailLevel


class TestXRayConfig:
    """Tests for XRayConfig dataclass."""

    def test_default_values(self) -> None:
        """Config has expected default values."""
        config = XRayConfig()
        assert config.base_url is None
        assert config.api_key is None
        assert config.buffer_size == 1000
        assert config.flush_interval == 5.0
        assert config.default_detail == DetailLevel.summary

    def test_custom_values(self) -> None:
        """Config accepts custom values."""
        config = XRayConfig(
            base_url="http://localhost:9000",
            api_key="test-key",
            buffer_size=500,
            flush_interval=10.0,
            default_detail=DetailLevel.full,
        )
        assert config.base_url == "http://localhost:9000"
        assert config.api_key == "test-key"
        assert config.buffer_size == 500
        assert config.flush_interval == 10.0
        assert config.default_detail == DetailLevel.full


class TestLoadConfig:
    """Tests for load_config function."""

    def test_defaults_with_no_config_file(self, tmp_path: Path, monkeypatch) -> None:
        """Load config returns defaults when no config file exists."""
        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config.base_url is None
        assert config.buffer_size == 1000

    def test_loads_from_yaml_file(self, tmp_path: Path) -> None:
        """Config loads from explicit YAML file."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            """
sdk:
  base_url: http://yaml-url:8000
  api_key: yaml-key
  buffer_size: 3000
  flush_interval: 10.0
  default_detail: full
"""
        )

        config = load_config(config_file=config_file)
        assert config.base_url == "http://yaml-url:8000"
        assert config.api_key == "yaml-key"
        assert config.buffer_size == 3000
        assert config.flush_interval == 10.0
        assert config.default_detail == DetailLevel.full

    def test_auto_discovers_config_file(self, tmp_path: Path, monkeypatch) -> None:
        """Config auto-discovers xray.config.yaml from cwd."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text(
            """
sdk:
  base_url: http://discovered:8000
  buffer_size: 2000
"""
        )
        monkeypatch.chdir(tmp_path)

        config = load_config()
        assert config.base_url == "http://discovered:8000"
        assert config.buffer_size == 2000

    def test_kwargs_override_yaml(self, tmp_path: Path) -> None:
        """Explicit kwargs override YAML values."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            """
sdk:
  base_url: http://yaml-url:8000
  buffer_size: 3000
"""
        )

        config = load_config(
            config_file=config_file,
            base_url="http://override:9000",
        )
        assert config.base_url == "http://override:9000"
        assert config.buffer_size == 3000  # From YAML

    def test_nonexistent_yaml_file_uses_defaults(self) -> None:
        """Nonexistent YAML file results in defaults."""
        config = load_config(config_file="/nonexistent/path.yaml")
        assert config.buffer_size == 1000

    def test_type_conversions(self, tmp_path: Path) -> None:
        """String values are converted to correct types."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            """
sdk:
  buffer_size: "999"
  flush_interval: "7.5"
"""
        )

        config = load_config(config_file=config_file)
        assert config.buffer_size == 999
        assert isinstance(config.buffer_size, int)
        assert config.flush_interval == 7.5
        assert isinstance(config.flush_interval, float)

    def test_detail_level_conversion(self, tmp_path: Path) -> None:
        """Detail level string is converted to enum."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            """
sdk:
  default_detail: full
"""
        )

        config = load_config(config_file=config_file)
        assert config.default_detail == DetailLevel.full
        assert isinstance(config.default_detail, DetailLevel)

    def test_none_kwargs_dont_override(self, tmp_path: Path) -> None:
        """None kwargs don't override YAML values."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            """
sdk:
  base_url: http://yaml-url:8000
"""
        )

        config = load_config(config_file=config_file, base_url=None)
        assert config.base_url == "http://yaml-url:8000"

    def test_ignores_api_section(self, tmp_path: Path) -> None:
        """SDK config ignores api section."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            """
sdk:
  base_url: http://sdk:8000
api:
  database_url: postgresql://localhost/xray
"""
        )

        config = load_config(config_file=config_file)
        assert config.base_url == "http://sdk:8000"
        # Verify api section doesn't leak into SDK config
        assert not hasattr(config, "database_url")


class TestConfigImports:
    """Tests for config module imports."""

    def test_importable_from_sdk(self) -> None:
        """Config classes can be imported from sdk package."""
        from sdk import XRayConfig, load_config

        assert XRayConfig is not None
        assert load_config is not None
