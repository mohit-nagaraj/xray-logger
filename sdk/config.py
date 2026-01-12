"""SDK configuration. Reads from `xray.config.yaml` under the `sdk:` section.

Environment variables take precedence over config file:
- XRAY_API_KEY: API key for authentication
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from shared.config import find_config_file, get_section, load_yaml_file


class XRayConfig(BaseModel):
    """SDK configuration for X-Ray client."""

    base_url: str | None = None
    api_key: str | None = None
    buffer_size: int = 1000
    flush_interval: float = 5.0
    batch_size: int = 100
    http_timeout: float = 30.0


def load_config(config_file: str | Path | None = None) -> XRayConfig:
    """Load SDK configuration from xray.config.yaml.

    Environment variables take precedence over config file values.
    """
    if config_file:
        yaml_config = load_yaml_file(config_file)
    else:
        found_file = find_config_file()
        yaml_config = load_yaml_file(found_file) if found_file else {}

    config: dict[str, Any] = get_section(yaml_config, "sdk")

    # Environment variables override config file
    if api_key := os.environ.get("XRAY_API_KEY"):
        config["api_key"] = api_key

    return XRayConfig(**config)
