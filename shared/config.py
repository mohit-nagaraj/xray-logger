"""Shared configuration utilities for X-Ray SDK and API.

Both SDK and API read from a single config file: `xray.config.yaml` in the project root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

CONFIG_FILENAME = "xray.config.yaml"


def find_config_file(start_path: Path | None = None) -> Path | None:
    """Find xray.config.yaml by searching from start_path up to root."""
    current = Path(start_path) if start_path else Path.cwd()

    for parent in [current, *current.parents]:
        config_path = parent / CONFIG_FILENAME
        if config_path.exists():
            return config_path

    return None


def load_yaml_file(config_file: str | Path) -> dict[str, Any]:
    """Load configuration from a YAML file."""
    import yaml

    path = Path(config_file)
    if not path.exists():
        return {}

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_section(config: dict[str, Any], section: str) -> dict[str, Any]:
    """Extract a section from config dict."""
    return config.get(section, {}) if isinstance(config.get(section), dict) else {}
