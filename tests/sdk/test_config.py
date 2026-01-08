"""Tests for SDK configuration."""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from sdk.config import XRayConfig, load_config
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

    def test_defaults_with_no_args(self) -> None:
        """Load config returns defaults when no args provided."""
        config = load_config()
        assert config.base_url is None
        assert config.buffer_size == 1000

    def test_env_var_override(self) -> None:
        """Environment variables override defaults."""
        env = {
            "XRAY_BASE_URL": "http://env-url:8080",
            "XRAY_API_KEY": "env-key",
            "XRAY_BUFFER_SIZE": "2000",
            "XRAY_FLUSH_INTERVAL": "15.0",
            "XRAY_DEFAULT_DETAIL": "full",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            config = load_config()

        assert config.base_url == "http://env-url:8080"
        assert config.api_key == "env-key"
        assert config.buffer_size == 2000
        assert config.flush_interval == 15.0
        assert config.default_detail == DetailLevel.full

    def test_kwargs_override_env_vars(self) -> None:
        """Explicit kwargs take priority over env vars."""
        env = {"XRAY_BASE_URL": "http://env-url:8080"}
        with mock.patch.dict(os.environ, env, clear=False):
            config = load_config(base_url="http://kwarg-url:9090")

        assert config.base_url == "http://kwarg-url:9090"

    def test_yaml_file_loading(self) -> None:
        """Config loads from YAML file."""
        yaml_content = """
base_url: http://yaml-url:8000
api_key: yaml-key
buffer_size: 3000
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = f.name

        try:
            config = load_config(config_file=yaml_path)
            assert config.base_url == "http://yaml-url:8000"
            assert config.api_key == "yaml-key"
            assert config.buffer_size == 3000
        finally:
            os.unlink(yaml_path)

    def test_env_vars_override_yaml(self) -> None:
        """Env vars take priority over YAML file."""
        yaml_content = """
base_url: http://yaml-url:8000
api_key: yaml-key
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = f.name

        try:
            env = {"XRAY_BASE_URL": "http://env-url:9000"}
            with mock.patch.dict(os.environ, env, clear=False):
                config = load_config(config_file=yaml_path)

            # Env var wins
            assert config.base_url == "http://env-url:9000"
            # YAML still applies for others
            assert config.api_key == "yaml-key"
        finally:
            os.unlink(yaml_path)

    def test_kwargs_override_yaml_and_env(self) -> None:
        """Kwargs override both YAML and env vars."""
        yaml_content = "base_url: http://yaml-url:8000"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = f.name

        try:
            env = {"XRAY_BASE_URL": "http://env-url:9000"}
            with mock.patch.dict(os.environ, env, clear=False):
                config = load_config(
                    config_file=yaml_path, base_url="http://kwarg-url:7000"
                )

            assert config.base_url == "http://kwarg-url:7000"
        finally:
            os.unlink(yaml_path)

    def test_nonexistent_yaml_file_ignored(self) -> None:
        """Nonexistent YAML file is silently ignored."""
        config = load_config(config_file="/nonexistent/path.yaml")
        # Should return defaults without error
        assert config.buffer_size == 1000

    def test_type_conversions(self) -> None:
        """String values are converted to correct types."""
        env = {
            "XRAY_BUFFER_SIZE": "999",
            "XRAY_FLUSH_INTERVAL": "7.5",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            config = load_config()

        assert config.buffer_size == 999
        assert isinstance(config.buffer_size, int)
        assert config.flush_interval == 7.5
        assert isinstance(config.flush_interval, float)

    def test_detail_level_conversion(self) -> None:
        """Detail level string is converted to enum."""
        config = load_config(default_detail="full")
        assert config.default_detail == DetailLevel.full
        assert isinstance(config.default_detail, DetailLevel)

    def test_none_kwargs_ignored(self) -> None:
        """None kwargs don't override existing values."""
        env = {"XRAY_BASE_URL": "http://env-url:8080"}
        with mock.patch.dict(os.environ, env, clear=False):
            config = load_config(base_url=None)

        # None kwarg shouldn't override env var
        assert config.base_url == "http://env-url:8080"


class TestConfigImports:
    """Tests for config module imports."""

    def test_importable_from_sdk(self) -> None:
        """Config classes can be imported from sdk package."""
        from sdk import XRayConfig, load_config

        assert XRayConfig is not None
        assert load_config is not None
