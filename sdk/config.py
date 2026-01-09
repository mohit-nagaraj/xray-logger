"""SDK configuration. Reads from `xray.config.yaml` under the `sdk:` section."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from shared.config import find_config_file, get_section, load_yaml_file
from shared.types import DetailLevel


class XRayConfig(BaseModel):
    """SDK configuration for X-Ray client."""

    base_url: str | None = None
    api_key: str | None = None
    buffer_size: int = 1000
    flush_interval: float = 5.0
    batch_size: int = 100
    http_timeout: float = 30.0
    default_detail: DetailLevel = DetailLevel.summary


def load_config(config_file: str | Path | None = None) -> XRayConfig:
    """Load SDK configuration from xray.config.yaml."""
    if config_file:
        yaml_config = load_yaml_file(config_file)
    else:
        found_file = find_config_file()
        yaml_config = load_yaml_file(found_file) if found_file else {}

    config: dict[str, Any] = get_section(yaml_config, "sdk")

    return XRayConfig(**config)
