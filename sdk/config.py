"""SDK configuration. Reads from `xray.config.yaml` under the `sdk:` section."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shared.config import find_config_file, get_section, load_yaml_file

if TYPE_CHECKING:
    from shared.types import DetailLevel


@dataclass
class XRayConfig:
    """SDK configuration for X-Ray client."""

    base_url: str | None = None
    api_key: str | None = None
    buffer_size: int = 1000
    flush_interval: float = 5.0
    default_detail: DetailLevel = field(default_factory=lambda: _get_default_detail_level())


def _get_default_detail_level() -> DetailLevel:
    from shared.types import DetailLevel
    return DetailLevel.summary


def load_config(config_file: str | Path | None = None) -> XRayConfig:
    """Load SDK configuration from xray.config.yaml."""
    from shared.types import DetailLevel

    if config_file:
        yaml_config = load_yaml_file(config_file)
    else:
        found_file = find_config_file()
        yaml_config = load_yaml_file(found_file) if found_file else {}

    config: dict[str, Any] = get_section(yaml_config, "sdk")

    if "buffer_size" in config:
        config["buffer_size"] = int(config["buffer_size"])
    if "flush_interval" in config:
        config["flush_interval"] = float(config["flush_interval"])
    if "default_detail" in config and isinstance(config["default_detail"], str):
        config["default_detail"] = DetailLevel(config["default_detail"])

    return XRayConfig(**config)
