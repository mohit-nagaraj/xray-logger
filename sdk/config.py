"""SDK configuration.

Reads from `xray.config.yaml` in project root under the `sdk:` section.

Configuration priority (highest to lowest):
1. Explicit kwargs passed to load_config()
2. xray.config.yaml file (auto-discovered)
3. Default values
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from shared.config import find_config_file, get_section, load_yaml_file

if TYPE_CHECKING:
    from shared.types import DetailLevel


@dataclass
class XRayConfig:
    """SDK configuration for X-Ray client.

    Attributes:
        base_url: API endpoint URL (required for sending data).
        api_key: Optional API key for authentication.
        buffer_size: Max events to buffer before dropping (default: 1000).
        flush_interval: Seconds between buffer flushes (default: 5.0).
        default_detail: Default payload detail level (default: summary).
    """

    base_url: str | None = None
    api_key: str | None = None
    buffer_size: int = 1000
    flush_interval: float = 5.0
    default_detail: DetailLevel = field(default_factory=lambda: _get_default_detail_level())


def _get_default_detail_level() -> DetailLevel:
    """Lazy import to avoid circular dependency."""
    from shared.types import DetailLevel

    return DetailLevel.summary


def load_config(
    config_file: str | Path | None = None,
    **overrides: Any,
) -> XRayConfig:
    """Load SDK configuration from xray.config.yaml.

    Args:
        config_file: Optional explicit path to config file.
                     If not provided, auto-discovers xray.config.yaml from cwd.
        **overrides: Direct config overrides (highest priority).

    Returns:
        XRayConfig instance.

    Example:
        # Auto-discover config from project root
        config = load_config()

        # Explicit config file
        config = load_config("path/to/xray.config.yaml")

        # Programmatic override
        config = load_config(base_url="http://localhost:9000")
    """
    from shared.types import DetailLevel

    config: dict[str, Any] = {}

    # 1. Load from YAML file
    if config_file:
        yaml_config = load_yaml_file(config_file)
    else:
        # Auto-discover config file
        found_file = find_config_file()
        yaml_config = load_yaml_file(found_file) if found_file else {}

    # Extract sdk section
    config.update(get_section(yaml_config, "sdk"))

    # 2. Override with explicit kwargs (highest priority)
    config.update({k: v for k, v in overrides.items() if v is not None})

    # Type conversions
    if "buffer_size" in config:
        config["buffer_size"] = int(config["buffer_size"])
    if "flush_interval" in config:
        config["flush_interval"] = float(config["flush_interval"])
    if "default_detail" in config and isinstance(config["default_detail"], str):
        config["default_detail"] = DetailLevel(config["default_detail"])

    return XRayConfig(**config)
