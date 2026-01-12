# Product Recommendation Pipeline Example

A multi-step recommendation pipeline instrumented with the X-Ray SDK. Demonstrates decision-level observability including filtering criteria, ranking scores, and reasoning.

## Pipeline Flow

```
get_candidates (retrieval)
    → filter_products (filter)
        → rank_products (rank)
            → format_response (transform)
```

## Quick Start

### 1. Start the X-Ray Backend

From the project root:

```bash
docker-compose up -d
```

This starts:
- PostgreSQL database on port 5433 (host)
- X-Ray API server on port 8000

### 2. Install Dependencies

```bash
cd examples/recommendation-pipeline
pip install -r requirements.txt
```

### 3. Run the Pipeline

```bash
python main.py
```

## What Gets Captured

Each pipeline run captures:

- **Run metadata**: pipeline name, input parameters, user_id, timestamps
- **Step data for each stage**:
  - `get_candidates`: input category, output count
  - `filter_products`: filter criteria, removed items with reasons
  - `rank_products`: ranking formula, score breakdown, candidate list
  - `format_response`: final output shape

## Example Output

```
[Run 1] Recommendations for 'electronics' (min_rating=4.0)
--------------------------------------------------
Found 3 recommendations:
  - Wireless Headphones Pro: $149.99 (rating: 4.7, score: 0.848)
  - Bluetooth Speaker Mini: $49.99 (rating: 4.1, score: 0.832)
  - Noise Cancelling Buds: $199.99 (rating: 4.5, score: 0.780)
```

## Viewing Captured Data

After running the pipeline, data is stored in PostgreSQL. Connect to the database:

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U xray -d xray

# Query runs
SELECT id, pipeline_name, status, started_at FROM runs ORDER BY started_at DESC;

# Query steps with their runs
SELECT s.step_name, s.step_type, s.input_count, s.output_count, s.status
FROM steps s
JOIN runs r ON s.run_id = r.id
ORDER BY r.started_at DESC, s.index;
```

## SDK Features Demonstrated

| Feature | Location | Purpose |
|---------|----------|---------|
| `@step` decorator | `pipeline.py` | Auto-instrument functions |
| `attach_reasoning()` | `filter_products`, `rank_products` | Explain WHY decisions were made |
| `attach_candidates()` | `rank_products` | Capture ranked results with scores |
| `client.start_run()` | `main.py` | Create run context |
| `shutdown_xray()` | `main.py` | Graceful shutdown with flush |
