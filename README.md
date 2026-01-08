# X-Ray SDK & API

Decision-reasoning observability for multi-step pipelines.

## Installation

```bash
# Install everything
pip install -e .

# With dev tools (pytest, mypy, ruff)
pip install -e ".[dev]"
```

## Configuration

Create `xray.config.yaml` in your project root:

```yaml
sdk:
  base_url: http://localhost:8000
  api_key: your-api-key        # Optional
  buffer_size: 1000            # Max events to buffer (default: 1000)
  flush_interval: 5.0          # Seconds between flushes (default: 5.0)
  default_detail: summary      # summary | full (default: summary)

api:
  database_url: postgresql+asyncpg://localhost:5432/xray
  debug: false
```

### Configuration Options

| Section | Field | Description | Default |
|---------|-------|-------------|---------|
| `sdk` | `base_url` | API endpoint URL | (none) |
| `sdk` | `api_key` | Authentication key | (none) |
| `sdk` | `buffer_size` | Max buffered events | 1000 |
| `sdk` | `flush_interval` | Flush interval (seconds) | 5.0 |
| `sdk` | `default_detail` | Payload detail level | summary |
| `api` | `database_url` | Database connection URL | postgresql+asyncpg://localhost:5432/xray |
| `api` | `debug` | Enable debug mode | false |

### Local Development with SQLite

```yaml
api:
  database_url: sqlite+aiosqlite:///./xray.db
  debug: true
```

## Quick Start

### SDK Usage

```python
from sdk import load_config

# Auto-discovers xray.config.yaml from project root
config = load_config()

# Or with programmatic override
config = load_config(base_url="http://localhost:9000")
```

### API Usage

```python
from api import load_config

# Auto-discovers xray.config.yaml from project root
config = load_config()

# For local development
config = load_config(database_url="sqlite+aiosqlite:///./xray.db")
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy shared sdk api

# Lint
ruff check .
```

## Project Structure

```
/
├── pyproject.toml      # Project config and dependencies
├── xray.config.yaml    # User config file (create this)
├── shared/             # Shared types and utilities
│   ├── types.py        # StepType, RunStatus, StepStatus, DetailLevel
│   └── config.py       # Config file discovery and parsing
├── sdk/                # SDK for instrumenting pipelines
│   └── config.py       # XRayConfig
├── api/                # API backend
│   └── config.py       # APIConfig
└── tests/              # Test suite
```
