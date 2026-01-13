# X-Ray Logger

**Decision-level observability for ML/LLM pipelines.**

X-Ray captures *why* decisions were made—candidates considered, filters applied, scores computed, and reasoning behind each step—not just what functions ran.

## Quick Start

### 1. Start the Server

**Option A: Docker Compose (Recommended - with PostgreSQL)**

```bash
# Download docker-compose.yml
curl -O https://raw.githubusercontent.com/mohit-nagaraj/xray-logger/main/docker-compose.yml

# Start services (PostgreSQL + X-Ray API)
docker-compose up -d
```

**Option B: Docker Run (SQLite)**

```bash
docker run -d -p 8000:8000 \
  -e XRAY_DATABASE_URL=sqlite+aiosqlite:///./xray.db \
  ghcr.io/mohit-nagaraj/xray-logger:latest
```

### 2. Install the SDK

```bash
pip install xray-logger
```

### 3. Instrument Your Code

```python
from xray_logger import init_xray, step, attach_reasoning

client = init_xray(base_url="http://localhost:8000")

@step(step_type="filter")
def filter_items(items, threshold=0.5):
    result = [i for i in items if i["score"] >= threshold]
    attach_reasoning({"threshold": threshold, "removed": len(items) - len(result)})
    return result

with client.start_run("my-pipeline"):
    filtered = filter_items(items)
```

## Features

- **Decision Transparency** - Capture candidates, scores, and reasoning at each step
- **Lightweight SDK** - Simple decorators, fail-open design
- **FastAPI Middleware** - Automatic HTTP request instrumentation
- **Query API** - Filter runs by pipeline, user, status

## Documentation

- [Quick Start Guide](https://github.com/mohit-nagaraj/xray-logger/wiki/Quick-Start)
- [Architecture](https://github.com/mohit-nagaraj/xray-logger/wiki/Architecture)
- [Examples](./examples)

## Step Types

| Type | Use Case |
|------|----------|
| `filter` | Removing candidates by criteria |
| `rank` | Ordering candidates by score |
| `llm` | LLM/AI model calls |
| `retrieval` | Fetching external data |
| `transform` | Data transformations |

## Development

For local development with source code:

```bash
git clone https://github.com/mohit-nagaraj/xray-logger.git
cd xray-logger

# Use dev compose (builds from source)
docker-compose -f docker-compose.dev.yml up -d
```

## License

MIT
