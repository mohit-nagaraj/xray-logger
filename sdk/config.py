"""SDK configuration with support for environment variables and YAML files.

Configuration priority (highest to lowest):
1. Explicit kwargs passed to load_config()
2. Environment variables (XRAY_*)
3. YAML config file (if provided)
4. Default values
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shared.types import DetailLevel


@dataclass
class XRayConfig:
    """SDK configuration for X-Ray client.

    Attributes:
        base_url: API endpoint URL. Must be configured (no default).
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
) -> XRayConfig:
    """Load SDK configuration with priority: overrides > env vars > yaml > defaults.

    Args:
        config_file: Optional path to YAML config file.
        **overrides: Direct config overrides (highest priority).

    Returns:
        XRayConfig instance.

    Example:
        # From environment variables
        config = load_config()

        # From YAML file with overrides
        config = load_config("xray.yaml", api_key="override-key")

        # Explicit configuration
        config = load_config(base_url="http://localhost:8000")
    """
    from shared.types import DetailLevel

    config: dict[str, Any] = {}

    # 1. Load from YAML file (lowest priority after defaults)
    if config_file:
        config.update(_load_yaml_config(config_file))

    # 2. Override with environment variables
    env_mapping = {
        "base_url": "XRAY_BASE_URL",
        "api_key": "XRAY_API_KEY",
        "buffer_size": "XRAY_BUFFER_SIZE",
        "flush_interval": "XRAY_FLUSH_INTERVAL",
        "default_detail": "XRAY_DEFAULT_DETAIL",
    }

    for key, env_var in env_mapping.items():
        if env_val := os.getenv(env_var):
            config[key] = env_val

    # 3. Override with explicit kwargs (highest priority)
    config.update({k: v for k, v in overrides.items() if v is not None})

    # Type conversions
    if "buffer_size" in config:
        config["buffer_size"] = int(config["buffer_size"])
    if "flush_interval" in config:
        config["flush_interval"] = float(config["flush_interval"])
    if "default_detail" in config and isinstance(config["default_detail"], str):
        config["default_detail"] = DetailLevel(config["default_detail"])

    return XRayConfig(**config)
