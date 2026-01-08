# X-Ray Architecture

## Package Structure

```
xray/
├── shared/     # Shared types & utilities (build-time only)
├── sdk/        # Client library for instrumentation
└── api/        # Server for storage & queries
```

## Installation

```bash
# For instrumenting your ML pipelines (lightweight)
pip install xray[sdk]

# For running the API server directly
pip install xray[api]

# For development (includes both + dev tools)
pip install -e ".[all]"
```

| Extra | Use Case | Dependencies Added |
|-------|----------|-------------------|
| `[sdk]` | Instrument pipelines | httpx |
| `[api]` | Run API server | fastapi, sqlalchemy, asyncpg, uvicorn |
| `[dev]` | Development | pytest, mypy, ruff |
| `[all]` | Everything | sdk + api + dev |

**Note**: Base dependencies (pyyaml, pydantic) are always installed.

## Component Separation

| Component | What it does | How it runs |
|-----------|--------------|-------------|
| **SDK** | Library imported into user's app to instrument pipelines | Runs IN user's process |
| **API** | Server that receives + stores observability data | Runs as SEPARATE service |
| **shared** | Common types (enums) and config utilities | Bundled into both at build time |

### Key Points

- **SDK does NOT auto-start the API** - that would cause unexpected behavior and port conflicts
- **shared** is compile-time code sharing only - no runtime coupling
- SDK and API can be deployed completely independently
- Both read from the same config file format (`xray.config.yaml`) but run separately

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        User's Application                        │
│                                                                  │
│   from sdk import step, XRayClient                              │
│                                                                  │
│   @step(type="filter")                                          │
│   def filter_candidates(items):                                 │
│       ...                                                        │
│                                                                  │
│   SDK captures: input_count, output_count, timing, metadata     │
│                              │                                   │
└──────────────────────────────│───────────────────────────────────┘
                               │ HTTP POST (async, buffered)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        X-Ray API Server                          │
│                                                                  │
│   POST /runs                                                     │
│   POST /runs/{id}/steps                                         │
│   GET  /runs, /steps (query)                                    │
│                              │                                   │
└──────────────────────────────│───────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         PostgreSQL                               │
│                                                                  │
│   Tables: runs, steps                                           │
└─────────────────────────────────────────────────────────────────┘
```

## Running Locally

### Option 1: Docker Compose (Recommended)

```yaml
# docker-compose.yml
services:
  xray-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/xray
    depends_on:
      - db

  db:
    image: postgres:16
    environment:
      - POSTGRES_DB=xray
      - POSTGRES_PASSWORD=postgres
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

```bash
# Start API + database
docker-compose up -d

# View logs
docker-compose logs -f xray-api
```

### Option 2: Manual Setup

```bash
# 1. Start PostgreSQL (or use existing instance)
docker run -d --name xray-db \
  -e POSTGRES_DB=xray \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:16

# 2. Configure database URL
# In xray.config.yaml:
api:
  database_url: postgresql+asyncpg://postgres:postgres@localhost:5432/xray

# 3. Start API server
python -m api
```

### Option 3: SQLite for Quick Testing

```yaml
# xray.config.yaml
api:
  database_url: sqlite+aiosqlite:///./xray.db
```

```bash
python -m api
```

## Production Deployment

### API Server

Deploy as a standalone service:

- **Container**: Docker/Kubernetes
- **Serverless**: AWS Lambda, Google Cloud Run
- **PaaS**: Heroku, Railway, Render

Example Kubernetes deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: xray-api
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: xray-api
          image: your-registry/xray-api:latest
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: xray-secrets
                  key: database-url
          ports:
            - containerPort: 8000
```

### Database

Use managed PostgreSQL:

- **AWS**: RDS PostgreSQL
- **GCP**: Cloud SQL
- **Azure**: Azure Database for PostgreSQL
- **Other**: Supabase, Neon, PlanetScale

### SDK in User Applications

Users install the package and configure:

```yaml
# xray.config.yaml (in user's project root)
sdk:
  base_url: https://xray-api.yourcompany.com
  api_key: ${XRAY_API_KEY}  # From environment
  buffer_size: 1000
  flush_interval: 5.0
```

```python
# User's code
from sdk import step, XRayClient

client = XRayClient()  # Reads from xray.config.yaml

@step(type="filter")
def my_filter(items):
    return [x for x in items if x.score > 0.5]
```

## Configuration

Both SDK and API read from `xray.config.yaml`:

```yaml
# SDK configuration
sdk:
  base_url: http://localhost:8000
  api_key: your-api-key
  buffer_size: 1000
  flush_interval: 5.0
  default_detail: summary  # or "full"

# API configuration
api:
  database_url: postgresql+asyncpg://localhost:5432/xray
  debug: false
```

### Config File Discovery

The config file is found by searching from the current directory up to the filesystem root:

```
/home/user/myproject/src/main.py  (running here)
         ↓ searches upward
/home/user/myproject/xray.config.yaml  (found!)
```

## Fail-Open Design

The SDK is designed to never break user applications:

- **Buffered transport**: Data is batched and sent asynchronously
- **Fail-open**: If API is unavailable, SDK silently drops data
- **No blocking**: Instrumented code never waits for API responses
- **Graceful degradation**: Missing config = SDK disabled, not crashed

```python
# This works even if API is down
@step(type="llm")
def call_openai(prompt):
    return openai.chat(prompt)  # Never blocked by X-Ray
```
