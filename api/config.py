"""API server configuration.

Reads from `xray.config.yaml` in project root under the `api:` section.

Configuration priority (highest to lowest):
1. Explicit kwargs passed to load_config()
2. xray.config.yaml file (auto-discovered)
3. Default values
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.config import find_config_file, get_section, load_yaml_file


@dataclass
class APIConfig:
    """API server configuration.

    Attributes:
        database_url: Full database connection URL.
                      Default: PostgreSQL on localhost:5432/xray
                      For local dev: sqlite+aiosqlite:///./xray.db
        debug: Enable debug mode (default: False).
    """

    database_url: str = "postgresql+asyncpg://localhost:5432/xray"
    debug: bool = False


def load_config(
    config_file: str | Path | None = None,
    **overrides: Any,
) -> APIConfig:
    """Load API configuration from xray.config.yaml.

    Args:
        config_file: Optional explicit path to config file.
                     If not provided, auto-discovers xray.config.yaml from cwd.
        **overrides: Direct config overrides (highest priority).

    Returns:
        APIConfig instance.

    Example:
        # Auto-discover config from project root
        config = load_config()

        # For local development with SQLite
        config = load_config(database_url="sqlite+aiosqlite:///./xray.db")
    """
    config: dict[str, Any] = {}

    # 1. Load from YAML file
    if config_file:
        yaml_config = load_yaml_file(config_file)
    else:
        # Auto-discover config file
        found_file = find_config_file()
        yaml_config = load_yaml_file(found_file) if found_file else {}

    # Extract api section
    config.update(get_section(yaml_config, "api"))

    # 2. Override with explicit kwargs (highest priority)
    config.update({k: v for k, v in overrides.items() if v is not None})

    # Type conversions
    if "debug" in config:
        config["debug"] = (
            config["debug"]
            if isinstance(config["debug"], bool)
            else str(config["debug"]).lower() in ("true", "1", "yes")
        )

    return APIConfig(**config)
