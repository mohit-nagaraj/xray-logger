"""API server configuration with support for environment variables and YAML files.

Configuration priority (highest to lowest):
1. Explicit kwargs passed to load_config()
2. Environment variables (XRAY_*)
3. YAML config file (if provided)
4. Default values
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class APIConfig:
    """API server configuration.

    Attributes:
        database_url: Database connection URL (default: PostgreSQL on localhost).
        host: Server bind address (default: 0.0.0.0).
        port: Server port (default: 8000).
        debug: Enable debug mode (default: False).
    """

    database_url: str = "postgresql+asyncpg://localhost:5432/xray"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


def _load_yaml_config(config_file: str | Path) -> dict[str, Any]:
    """Load configuration from a YAML file."""
    try:
        import yaml
    except ImportError as err:
        raise ImportError(
            "PyYAML is required to load config files. Install with: pip install pyyaml"
        ) from err

    path = Path(config_file)
    if not path.exists():
        return {}

    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_config(
    config_file: str | Path | None = None,
    **overrides: Any,
) -> APIConfig:
    """Load API configuration with priority: overrides > env vars > yaml > defaults.

    Args:
        config_file: Optional path to YAML config file.
        **overrides: Direct config overrides (highest priority).

    Returns:
        APIConfig instance.

    Example:
        # From environment variables
        config = load_config()

        # From YAML file
        config = load_config("xray-api.yaml")

        # For local development with SQLite
        config = load_config(database_url="sqlite+aiosqlite:///./xray.db")
    """
    config: dict[str, Any] = {}

    # 1. Load from YAML file (lowest priority after defaults)
    if config_file:
        config.update(_load_yaml_config(config_file))

    # 2. Override with environment variables
    env_mapping = {
        "database_url": "XRAY_DATABASE_URL",
        "host": "XRAY_HOST",
        "port": "XRAY_PORT",
        "debug": "XRAY_DEBUG",
    }

    for key, env_var in env_mapping.items():
        if env_val := os.getenv(env_var):
            config[key] = env_val

    # 3. Override with explicit kwargs (highest priority)
    config.update({k: v for k, v in overrides.items() if v is not None})

    # Type conversions
    if "port" in config:
        config["port"] = int(config["port"])
    if "debug" in config:
        config["debug"] = (
            config["debug"]
            if isinstance(config["debug"], bool)
            else str(config["debug"]).lower() in ("true", "1", "yes")
        )

    return APIConfig(**config)
