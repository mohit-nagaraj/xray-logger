"""Shared configuration utilities for X-Ray SDK and API.

Both SDK and API read from a single config file: `xray.config.yaml` in the project root.

Configuration priority (highest to lowest):
1. Explicit kwargs passed to load functions
2. xray.config.yaml file (auto-discovered from cwd)
3. Default values

Example xray.config.yaml:
```yaml
sdk:
  base_url: http://localhost:8000
  api_key: your-api-key
  buffer_size: 1000
  flush_interval: 5.0
  default_detail: summary

api:
  database_url: postgresql+asyncpg://localhost:5432/xray
  debug: false
```
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Default config filename - users place this in their project root
CONFIG_FILENAME = "xray.config.yaml"


def find_config_file(start_path: Path | None = None) -> Path | None:
    """Find xray.config.yaml by searching from start_path up to root.

    Args:
        start_path: Directory to start search from (default: cwd).

    Returns:
        Path to config file if found, None otherwise.
    """
    current = Path(start_path) if start_path else Path.cwd()

    # Search current directory and parents
    for parent in [current, *current.parents]:
        config_path = parent / CONFIG_FILENAME
        if config_path.exists():
            return config_path

    return None


def load_yaml_file(config_file: str | Path) -> dict[str, Any]:
    """Load configuration from a YAML file.

    Args:
        config_file: Path to YAML config file.

    Returns:
        Parsed YAML content as dict, or empty dict if file doesn't exist.
    """
    import yaml

    path = Path(config_file)
    if not path.exists():
        return {}

    with open(path) as f:
        return yaml.safe_load(f) or {}


def get_section(config: dict[str, Any], section: str) -> dict[str, Any]:
    """Extract a section from config dict.

    Args:
        config: Full config dict.
        section: Section name ('sdk' or 'api').

    Returns:
        Section dict, or empty dict if not found.
    """
    return config.get(section, {}) if isinstance(config.get(section), dict) else {}
