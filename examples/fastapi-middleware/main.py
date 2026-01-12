#!/usr/bin/env python3
"""FastAPI Product API with X-Ray middleware example.

This example demonstrates how to use X-Ray SDK middleware to automatically
instrument a FastAPI application. The middleware creates Run contexts for
every HTTP request, enabling automatic observability without manual setup.

Usage:
    # Start X-Ray backend first (from project root)
    docker-compose up -d

    # Start this API
    cd examples/fastapi-middleware
    uvicorn main:app --reload --port 8001

    # Test endpoints
    curl http://localhost:8001/health
    curl http://localhost:8001/api/products

    # View captured data in X-Ray API
    curl http://localhost:8000/xray/runs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sdk import init_xray, load_config, shutdown_xray
from sdk.middleware import XRayMiddleware

from api import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    # Startup: Initialize X-Ray SDK from config file
    print("Loading X-Ray configuration from xray.config.yaml...")
    config = load_config()
    print(f"Configuration loaded: base_url={config.base_url}, buffer_size={config.buffer_size}")

    init_xray(config)
    print("X-Ray SDK initialized successfully")

    yield

    # Shutdown: Flush remaining events
    print("Shutting down X-Ray SDK...")
    shutdown_xray(timeout=5.0)
    print("X-Ray SDK shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Product API",
    description="Example API demonstrating X-Ray middleware for automatic observability",
    version="1.0.0",
    lifespan=lifespan,
)

# Add X-Ray middleware
# IMPORTANT: This must be added AFTER init_xray() is called
# The middleware will automatically:
# 1. Create a Run for every HTTP request
# 2. Set run name as: http:{method}:{path_template}
# 3. Capture HTTP metadata (status, duration, headers, etc.)
# 4. Make current_run() available in route handlers
app.add_middleware(
    XRayMiddleware,
    capture_headers=True,  # Capture request/response headers (sensitive ones redacted)
    path_template_extraction=True,  # Use /products/{id} instead of /products/123
)

# Include API routes
app.include_router(router, prefix="/api")


# Health check endpoint (no steps needed - demonstrates minimal overhead)
@app.get("/health")
async def health():
    """Health check endpoint.

    Demonstrates:
        - Middleware captures timing and metadata even for simple endpoints
        - No @step decorators needed for trivial operations
        - Minimal overhead for fast operations
    """
    return {
        "status": "healthy",
        "service": "product-api",
        "version": "1.0.0",
    }


# Root endpoint with documentation links
@app.get("/")
async def root():
    """API root with helpful links."""
    return {
        "message": "Product API - X-Ray Middleware Example",
        "docs": "/docs",
        "health": "/health",
        "api_endpoints": "/api/products",
        "xray_backend": "http://localhost:8000",
    }


if __name__ == "__main__":
    import uvicorn

    # Run the application
    # Use --reload for development to auto-restart on code changes
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
    )
