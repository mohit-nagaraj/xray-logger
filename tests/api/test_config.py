"""Tests for API configuration."""

import os
import tempfile
from unittest import mock

import pytest

from api.config import APIConfig, load_config


class TestAPIConfig:
    """Tests for APIConfig dataclass."""

    def test_default_values(self) -> None:
        """Config has expected default values."""
        config = APIConfig()
        assert config.database_url == "postgresql+asyncpg://localhost:5432/xray"
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.debug is False

    def test_custom_values(self) -> None:
        """Config accepts custom values."""
        config = APIConfig(
            database_url="sqlite+aiosqlite:///./test.db",
            host="127.0.0.1",
            port=9000,
            debug=True,
        )
        assert config.database_url == "sqlite+aiosqlite:///./test.db"
        assert config.host == "127.0.0.1"
        assert config.port == 9000
        assert config.debug is True


class TestLoadConfig:
    """Tests for load_config function."""

    def test_defaults_with_no_args(self) -> None:
        """Load config returns defaults when no args provided."""
        config = load_config()
        assert config.database_url == "postgresql+asyncpg://localhost:5432/xray"
        assert config.port == 8000
        assert config.debug is False

    def test_env_var_override(self) -> None:
        """Environment variables override defaults."""
        env = {
            "XRAY_DATABASE_URL": "postgresql+asyncpg://prod:5432/xray_prod",
            "XRAY_HOST": "0.0.0.0",
            "XRAY_PORT": "9000",
            "XRAY_DEBUG": "true",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            config = load_config()

        assert config.database_url == "postgresql+asyncpg://prod:5432/xray_prod"
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert config.debug is True

    def test_kwargs_override_env_vars(self) -> None:
        """Explicit kwargs take priority over env vars."""
        env = {"XRAY_PORT": "9000"}
        with mock.patch.dict(os.environ, env, clear=False):
            config = load_config(port=7000)

        assert config.port == 7000

    def test_yaml_file_loading(self) -> None:
        """Config loads from YAML file."""
        yaml_content = """
database_url: sqlite+aiosqlite:///./yaml.db
host: localhost
port: 8888
debug: true
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = f.name

        try:
            config = load_config(config_file=yaml_path)
            assert config.database_url == "sqlite+aiosqlite:///./yaml.db"
            assert config.host == "localhost"
            assert config.port == 8888
            assert config.debug is True
        finally:
            os.unlink(yaml_path)

    def test_env_vars_override_yaml(self) -> None:
        """Env vars take priority over YAML file."""
        yaml_content = """
database_url: sqlite+aiosqlite:///./yaml.db
port: 8888
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            yaml_path = f.name

        try:
            env = {"XRAY_PORT": "9999"}
            with mock.patch.dict(os.environ, env, clear=False):
                config = load_config(config_file=yaml_path)

            # Env var wins for port
            assert config.port == 9999
            # YAML still applies for database_url
            assert config.database_url == "sqlite+aiosqlite:///./yaml.db"
        finally:
            os.unlink(yaml_path)

    def test_nonexistent_yaml_file_ignored(self) -> None:
        """Nonexistent YAML file is silently ignored."""
        config = load_config(config_file="/nonexistent/path.yaml")
        # Should return defaults without error
        assert config.port == 8000

    def test_port_type_conversion(self) -> None:
        """Port string is converted to int."""
        env = {"XRAY_PORT": "12345"}
        with mock.patch.dict(os.environ, env, clear=False):
            config = load_config()

        assert config.port == 12345
        assert isinstance(config.port, int)

    def test_debug_flag_parsing_true(self) -> None:
        """Debug flag parses various truthy values."""
        for value in ["true", "True", "TRUE", "1", "yes", "Yes"]:
            env = {"XRAY_DEBUG": value}
            with mock.patch.dict(os.environ, env, clear=False):
                config = load_config()
            assert config.debug is True, f"Failed for value: {value}"

    def test_debug_flag_parsing_false(self) -> None:
        """Debug flag parses various falsy values."""
        for value in ["false", "False", "FALSE", "0", "no", "No", ""]:
            env = {"XRAY_DEBUG": value}
            with mock.patch.dict(os.environ, env, clear=False):
                config = load_config()
            assert config.debug is False, f"Failed for value: {value}"

    def test_debug_flag_bool_kwarg(self) -> None:
        """Debug flag accepts bool kwargs directly."""
        config = load_config(debug=True)
        assert config.debug is True

        config = load_config(debug=False)
        assert config.debug is False

    def test_none_kwargs_ignored(self) -> None:
        """None kwargs don't override existing values."""
        env = {"XRAY_PORT": "9000"}
        with mock.patch.dict(os.environ, env, clear=False):
            config = load_config(port=None)

        # None kwarg shouldn't override env var
        assert config.port == 9000

    def test_sqlite_for_local_development(self) -> None:
        """SQLite can be configured for local development."""
        config = load_config(database_url="sqlite+aiosqlite:///./xray.db")
        assert "sqlite" in config.database_url
        assert "aiosqlite" in config.database_url


class TestConfigImports:
    """Tests for config module imports."""

    def test_importable_from_api(self) -> None:
        """Config classes can be imported from api package."""
        from api import APIConfig, load_config

        assert APIConfig is not None
        assert load_config is not None
