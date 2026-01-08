# X-Ray SDK & API

Decision-reasoning observability for multi-step pipelines.

## Installation

```bash
# Install SDK only
pip install -e ".[sdk]"

# Install API only
pip install -e ".[api]"

# Install everything (SDK + API + dev tools)
pip install -e ".[all]"
```

## Quick Start

### SDK Usage

```python
from sdk import load_config

# Load config from environment variables
config = load_config()

# Or with explicit values
config = load_config(base_url="http://localhost:8000")
```

### API Usage

```python
from api import load_config

# Default: PostgreSQL
config = load_config()

# Local development: SQLite
config = load_config(database_url="sqlite+aiosqlite:///./xray.db")
```

## Configuration

Configuration priority (highest to lowest):
1. Explicit kwargs
2. Environment variables (`XRAY_*`)
3. YAML config file
4. Default values

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `XRAY_BASE_URL` | SDK API endpoint | (none) |
| `XRAY_API_KEY` | SDK authentication key | (none) |
| `XRAY_BUFFER_SIZE` | SDK event buffer size | 1000 |
| `XRAY_DATABASE_URL` | API database URL | postgresql+asyncpg://localhost:5432/xray |
| `XRAY_PORT` | API server port | 8000 |
| `XRAY_DEBUG` | API debug mode | false |

## Development

```bash
# Install with dev dependencies
pip install -e ".[all]"

# Run tests
pytest

# Type check
mypy shared sdk api

# Lint
ruff check .
```
