"""API server configuration. Reads from `xray.config.yaml` under the `api:` section."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.config import find_config_file, get_section, load_yaml_file


@dataclass
class APIConfig:
    """API server configuration."""

    database_url: str = "postgresql+asyncpg://localhost:5432/xray"
    debug: bool = False


def load_config(config_file: str | Path | None = None) -> APIConfig:
    """Load API configuration from xray.config.yaml."""
    if config_file:
        yaml_config = load_yaml_file(config_file)
    else:
        found_file = find_config_file()
        yaml_config = load_yaml_file(found_file) if found_file else {}

    config: dict[str, Any] = get_section(yaml_config, "api")

    if "debug" in config:
        config["debug"] = (
            config["debug"]
            if isinstance(config["debug"], bool)
            else str(config["debug"]).lower() in ("true", "1", "yes")
        )

    return APIConfig(**config)
