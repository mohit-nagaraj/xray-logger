# FastAPI Middleware Example

This example demonstrates how to use the **X-Ray SDK middleware** with FastAPI to automatically instrument HTTP endpoints for observability. The middleware eliminates the need for manual `client.start_run()` calls while still allowing you to use `@step` decorators for function-level instrumentation.

## Overview

**What This Example Shows:**

- ✅ Automatic Run creation for every HTTP request via `XRayMiddleware`
- ✅ HTTP-level observability (status codes, duration, headers, query params)
- ✅ Function-level observability using `@step` decorators within route handlers
- ✅ Custom metadata via `current_run()` in endpoints
- ✅ Error handling and exception capture
- ✅ Header capture with sensitive data redaction
- ✅ Comprehensive CRUD API patterns

## Quick Start

### Prerequisites

1. **X-Ray Backend Running:**
   ```bash
   # From project root
   docker-compose up -d
   ```

2. **Install Dependencies:**
   ```bash
   cd examples/fastapi-middleware
   pip install -r requirements.txt
   ```

### Run the API

```bash
uvicorn main:app --reload --port 8001
```

The API will be available at:
- API: http://localhost:8001
- API Docs: http://localhost:8001/docs
- Health Check: http://localhost:8001/health

## API Endpoints

### 1. List Products
```bash
# List all products
curl "http://localhost:8001/api/products"

# Filter by category
curl "http://localhost:8001/api/products?category=electronics"

# Filter by minimum rating
curl "http://localhost:8001/api/products?min_rating=4.5"

# Combine filters
curl "http://localhost:8001/api/products?category=books&min_rating=4.0"
```

**Demonstrates:**
- Query parameter capture
- `@step` decorated filtering logic
- Custom metadata via `current_run()`

### 2. Get Single Product
```bash
curl "http://localhost:8001/api/products/E001"

# Non-existent product (404)
curl "http://localhost:8001/api/products/INVALID"
```

**Demonstrates:**
- Path parameter capture
- Simple retrieval step
- 404 error handling

### 3. Create Product
```bash
curl -X POST "http://localhost:8001/api/products" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer demo-token-12345" \
  -d '{
    "name": "Mechanical Keyboard",
    "category": "electronics",
    "price": 89.99,
    "rating": 4.6,
    "in_stock": true
  }'
```

**Demonstrates:**
- Request body parsing and validation
- Validation step with `@step(step_type="filter")`
- Creation step with `@step(step_type="transform")`
- Custom metadata (client IP, operation type)
- Header capture (Authorization header will be redacted)

### 4. Update Product
```bash
curl -X PUT "http://localhost:8001/api/products/E001" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Wireless Headphones Pro Max",
    "price": 179.99
  }'
```

**Demonstrates:**
- Partial updates (only provided fields are updated)
- Path parameter + request body
- 404 for non-existent products

### 5. Error Handling Demo
```bash
curl -X DELETE "http://localhost:8001/api/products/E001/force-error"
```

**Demonstrates:**
- Exception capture by middleware
- Run status automatically set to "error"
- Error message captured in run metadata

### 6. Batch Create
```bash
curl -X POST "http://localhost:8001/api/products/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "products": [
      {
        "name": "USB-C Cable",
        "category": "electronics",
        "price": 12.99,
        "rating": 4.2,
        "in_stock": true
      },
      {
        "name": "Mouse Pad",
        "category": "home",
        "price": 14.99,
        "rating": 4.0,
        "in_stock": true
      }
    ]
  }'
```

**Demonstrates:**
- Batch operations with partial success
- Error collection without failing entire batch
- Custom batch metadata

## Key Features

### 1. Automatic Run Creation

The middleware automatically creates a Run context for every HTTP request:

```python
# No manual run management needed!
@router.get("/products")
async def list_products(category: str = None):
    # Run is AUTOMATICALLY active here via middleware
    products = list_products_with_filters(category=category)
    return products
```

**Run Naming Convention:** `http:{METHOD}:{path_template}`
- Examples:
  - `http:GET:/api/products`
  - `http:POST:/api/products`
  - `http:GET:/api/products/{product_id}`

### 2. HTTP Metadata Capture

The middleware automatically captures:
- `http.method` - HTTP method (GET, POST, etc.)
- `http.path` - Request path
- `http.status_code` - Response status code
- `http.duration_ms` - Request duration in milliseconds
- `http.client_host` - Client IP address
- `http.user_agent` - User agent string
- `http.request_headers` - Request headers (sensitive ones redacted)
- `http.response_headers` - Response headers (sensitive ones redacted)

### 3. Function-Level Steps

Use `@step` decorators within route handlers for detailed observability:

```python
from sdk import step, attach_reasoning

@step(step_type="retrieval")
def get_product_from_db(product_id: str) -> dict:
    """Retrieve product with reasoning capture."""
    product = PRODUCTS.get(product_id)

    attach_reasoning({
        "query_type": "primary_key_lookup",
        "product_id": product_id,
        "found": product is not None,
    })

    return product
```

### 4. Custom Metadata

Access the current run in route handlers to add custom metadata:

```python
from sdk import current_run

@router.post("/products")
async def create_product(product: ProductCreate, request: Request):
    run = current_run()
    if run:
        run.metadata["operation"] = "product_creation"
        run.metadata["category"] = product.category
        run.metadata["client_ip"] = request.client.host

    # ... rest of handler
```

### 5. Error Handling

The middleware automatically captures exceptions:

```python
@router.delete("/products/{product_id}/force-error")
async def force_error(product_id: str):
    run = current_run()
    if run:
        run.metadata["testing"] = "error_handling"

    # Exception is captured automatically
    # Run status is set to "error"
    raise ValueError("Intentional error for demonstration")
```

### 6. Header Redaction

Sensitive headers are automatically redacted for security:

**Captured Headers Example:**
```json
{
  "http.request_headers": {
    "user-agent": "curl/7.68.0",
    "content-type": "application/json",
    "authorization": "[REDACTED]",
    "x-api-key": "[REDACTED]",
    "cookie": "[REDACTED]"
  }
}
```

**Redacted Headers:**
- `authorization`
- `cookie`, `set-cookie`
- `x-api-key`, `x-auth-token`, `x-access-token`
- `x-csrf-token`, `x-xsrf-token`
- `proxy-authorization`

## Comparison: Before vs After

### Without Middleware (Manual)

```python
from sdk import init_xray, XRayConfig

client = init_xray(XRayConfig(base_url="http://localhost:8000"))

@app.get("/products")
async def list_products(category: str = None):
    # Manual run management required
    with client.start_run(
        pipeline_name="list-products",
        input_data={"category": category},
        metadata={
            "http.method": "GET",
            "http.path": "/products",
        },
    ) as run:
        try:
            products = list_products_with_filters(category=category)

            # Manual metadata updates
            run.metadata["http.status_code"] = 200
            run.metadata["result_count"] = len(products)

            return products

        except Exception as e:
            run.end_with_error(e)
            raise
```

**Problems:**
- 15+ lines of boilerplate per endpoint
- Manual metadata management
- Easy to forget instrumentation
- Inconsistent run naming
- Manual error handling

### With Middleware (Automatic)

```python
from sdk import init_xray, XRayConfig, current_run
from sdk.middleware import XRayMiddleware

# One-time setup
init_xray(XRayConfig(base_url="http://localhost:8000"))
app.add_middleware(XRayMiddleware)

@app.get("/products")
async def list_products(category: str = None):
    # Run automatically active!
    run = current_run()
    if run:
        run.metadata["operation"] = "list_products"

    # Use @step decorated functions
    products = list_products_with_filters(category=category)

    return products
```

**Benefits:**
- 5-7 lines of business logic
- Automatic run creation and cleanup
- Consistent run naming
- Automatic error capture
- HTTP metadata captured automatically

## Middleware Configuration

### Minimal Setup
```python
from sdk.middleware import XRayMiddleware

app.add_middleware(XRayMiddleware)
```

### Full Configuration
```python
app.add_middleware(
    XRayMiddleware,
    capture_headers=True,           # Capture request/response headers
    path_template_extraction=True,  # Use /products/{id} not /products/123
)
```

## Viewing Captured Data

### 1. View All HTTP Runs
```bash
curl "http://localhost:8000/xray/runs?limit=20"
```

### 2. View Runs for Specific Endpoint
```bash
# List products endpoint
curl "http://localhost:8000/xray/runs?pipeline=http:GET:/api/products"

# Create product endpoint
curl "http://localhost:8000/xray/runs?pipeline=http:POST:/api/products"
```

### 3. View Runs with Errors
```bash
curl "http://localhost:8000/xray/runs?status=error"
```

### 4. Get Detailed Run with All Steps
```bash
# Get run_id from previous query
curl "http://localhost:8000/xray/runs/{run_id}"
```

### 5. View Steps by Type
```bash
# View all validation steps
curl "http://localhost:8000/xray/steps?step_type=filter"

# View all retrieval steps
curl "http://localhost:8000/xray/steps?step_type=retrieval"

# View all transform steps
curl "http://localhost:8000/xray/steps?step_type=transform"
```

## Project Structure

```
fastapi-middleware/
├── README.md              # This file
├── requirements.txt       # Dependencies
├── main.py               # FastAPI app with middleware setup
├── api.py                # Route handlers (6 endpoints)
├── operations.py         # Business logic with @step decorators
└── data.py               # In-memory product store
```

## Architecture

```
HTTP Request
    ↓
XRayMiddleware
    ↓
[Creates Run automatically]
    ↓
Route Handler (api.py)
    ↓
current_run() available
    ↓
Business Logic (operations.py)
    ↓
@step decorators create Steps
    ↓
Transport buffers events
    ↓
Async flush to X-Ray API
    ↓
Stored in database
```

## Value Proposition

| Feature | Manual Instrumentation | With XRayMiddleware |
|---------|----------------------|-------------------|
| Setup per endpoint | ✅ Required | ❌ Not needed |
| Run naming | Manual | Automatic (`http:GET:/path`) |
| HTTP metadata | Manual capture | Automatic |
| Error handling | Manual try/catch | Automatic capture |
| Works with @step | ✅ Yes | ✅ Yes |
| Code verbosity | High (15-20 lines) | Low (5-7 lines) |
| Consistency | Varies by developer | Guaranteed consistent |
| Maintenance | Update every endpoint | Update middleware once |

## Testing Workflow

1. **Start X-Ray backend:**
   ```bash
   docker-compose up -d
   ```

2. **Start this API:**
   ```bash
   uvicorn main:app --reload --port 8001
   ```

3. **Make requests:**
   ```bash
   # Use curl commands from API Endpoints section above
   ```

4. **View data:**
   ```bash
   # Query X-Ray API
   curl "http://localhost:8000/xray/runs"
   ```

5. **Verify:**
   - Each request creates a Run
   - Run name follows `http:{method}:{path}` pattern
   - HTTP metadata is captured
   - `@step` decorators create Steps within Runs
   - Errors are captured with status="error"

## Key Takeaways

1. **Middleware eliminates boilerplate** - No need for `with client.start_run()` in every endpoint
2. **Comprehensive observability** - HTTP-level (middleware) + function-level (@step decorators)
3. **Fail-open design** - Middleware never crashes your application
4. **Security-conscious** - Sensitive headers automatically redacted
5. **Works seamlessly** - `@step` decorators and `current_run()` just work within middleware context
6. **Easy to adopt** - Add 2 lines to existing FastAPI apps for instant observability

## Next Steps

- Explore the code in `api.py` to see different endpoint patterns
- Check `operations.py` to see `@step` decorator usage
- Modify `main.py` to try different middleware configurations
- Query the X-Ray API to analyze captured data
- Try adding your own endpoints with instrumentation
