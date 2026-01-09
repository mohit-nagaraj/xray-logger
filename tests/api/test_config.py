"""Tests for API configuration."""

from pathlib import Path

import pytest

from api.config import APIConfig, load_config
from shared.config import CONFIG_FILENAME


class TestAPIConfig:
    """Tests for APIConfig dataclass."""

    def test_default_values(self) -> None:
        """Config has expected default values."""
        config = APIConfig()
        assert config.database_url == "postgresql+asyncpg://localhost:5432/xray"
        assert config.debug is False

    def test_custom_values(self) -> None:
        """Config accepts custom values."""
        config = APIConfig(
            database_url="sqlite+aiosqlite:///./test.db",
            debug=True,
        )
        assert config.database_url == "sqlite+aiosqlite:///./test.db"
        assert config.debug is True


class TestLoadConfig:
    """Tests for load_config function."""

    def test_defaults_with_no_config_file(self, tmp_path: Path, monkeypatch) -> None:
        """Load config returns defaults when no config file exists."""
        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config.database_url == "postgresql+asyncpg://localhost:5432/xray"
        assert config.debug is False

    def test_loads_from_yaml_file(self, tmp_path: Path) -> None:
        """Config loads from explicit YAML file."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            """
api:
  database_url: postgresql+asyncpg://prod:5432/xray_prod
  debug: true
"""
        )

        config = load_config(config_file=config_file)
        assert config.database_url == "postgresql+asyncpg://prod:5432/xray_prod"
        assert config.debug is True

    def test_auto_discovers_config_file(self, tmp_path: Path, monkeypatch) -> None:
        """Config auto-discovers xray.config.yaml from cwd."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text(
            """
api:
  database_url: sqlite+aiosqlite:///./discovered.db
"""
        )
        monkeypatch.chdir(tmp_path)

        config = load_config()
        assert config.database_url == "sqlite+aiosqlite:///./discovered.db"

    def test_nonexistent_yaml_file_uses_defaults(self) -> None:
        """Nonexistent YAML file results in defaults."""
        config = load_config(config_file="/nonexistent/path.yaml")
        assert config.database_url == "postgresql+asyncpg://localhost:5432/xray"

    def test_debug_flag_parsing_true(self, tmp_path: Path) -> None:
        """Debug flag parses various truthy values."""
        for value in ["true", "True", "TRUE", "1", "yes", "Yes"]:
            config_file = tmp_path / "test.yaml"
            config_file.write_text(f"api:\n  debug: {value}")
            config = load_config(config_file=config_file)
            assert config.debug is True, f"Failed for value: {value}"

    def test_debug_flag_parsing_false(self, tmp_path: Path) -> None:
        """Debug flag parses various falsy values."""
        for value in ["false", "False", "FALSE", "0", "no", "No"]:
            config_file = tmp_path / "test.yaml"
            config_file.write_text(f"api:\n  debug: {value}")
            config = load_config(config_file=config_file)
            assert config.debug is False, f"Failed for value: {value}"

    def test_sqlite_for_local_development(self, tmp_path: Path) -> None:
        """SQLite can be configured for local development."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(
            """
api:
  database_url: sqlite+aiosqlite:///./xray.db
"""
        )
        config = load_config(config_file=config_file)
        assert "sqlite" in config.database_url
        assert "aiosqlite" in config.database_url

    def test_ignores_sdk_section(self, tmp_path: Path) -> None:
        """API config ignores sdk section."""
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
        assert config.database_url == "postgresql://localhost/xray"
        assert not hasattr(config, "base_url")


class TestConfigImports:
    """Tests for config module imports."""

    def test_importable_from_api(self) -> None:
        """Config classes can be imported from api package."""
        from api import APIConfig, load_config

        assert APIConfig is not None
        assert load_config is not None
