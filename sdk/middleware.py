"""X-Ray middleware for FastAPI/Starlette applications.

This middleware automatically wraps HTTP requests in X-Ray Runs,
enabling automatic observability for web applications.

Usage:
    from fastapi import FastAPI
    from sdk import init_xray, XRayConfig
    from sdk.middleware import XRayMiddleware

    app = FastAPI()

    # Initialize X-Ray client
    init_xray(XRayConfig(base_url="http://localhost:8000"))

    # Add middleware
    app.add_middleware(XRayMiddleware)

    @app.get("/api/users")
    async def get_users():
        # current_run() is automatically available here
        return {"users": [...]}
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .client import get_client

if TYPE_CHECKING:
    from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class XRayMiddleware(BaseHTTPMiddleware):
    """Middleware that wraps HTTP requests in X-Ray Runs.

    This middleware automatically creates a Run for each HTTP request,
    making the run context available to all route handlers and downstream
    code via current_run().

    Run Naming Convention:
        - Format: "http:{method}:{path_template}"
        - Examples:
            - "http:GET:/api/users"
            - "http:POST:/api/users/{user_id}"
            - "http:GET:/health"

    Metadata Captured:
        - http.method: HTTP method (GET, POST, etc.)
        - http.path: Request path
        - http.status_code: Response status code
        - http.duration_ms: Request duration in milliseconds
        - http.client_host: Client IP address (if available)
        - http.user_agent: User agent string (if capture_headers=True)

    Error Handling:
        - Middleware is fail-open: if X-Ray client is not initialized or
          errors occur, the request proceeds normally
        - Exceptions from application code are captured in the run and re-raised
        - Middleware itself never crashes the application

    Example:
        app = FastAPI()
        app.add_middleware(XRayMiddleware)

        @app.get("/api/recommendations")
        async def get_recommendations():
            # X-Ray run is automatically active here
            run = current_run()
            # ... use SDK decorators or manual steps ...
            return {"recommendations": [...]}
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        capture_headers: bool = False,
        path_template_extraction: bool = True,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI application
            capture_headers: If True, capture request/response headers in metadata
            path_template_extraction: If True, attempt to extract route pattern
                instead of raw path (e.g., "/users/{id}" vs "/users/123")
        """
        super().__init__(app)
        self._capture_headers = capture_headers
        self._path_template_extraction = path_template_extraction

    async def dispatch(
        self, request: Request, call_next
    ) -> Response:
        """Process the request and wrap it in an X-Ray Run.

        Args:
            request: The incoming HTTP request
            call_next: Callable to invoke the next middleware/handler

        Returns:
            The HTTP response
        """
        # Get the global X-Ray client
        client = get_client()

        # Fail-open: if client not initialized, pass through
        if client is None or not client.is_started:
            logger.debug("X-Ray client not initialized, skipping instrumentation")
            return await call_next(request)

        # Extract path template if available (FastAPI stores this in request.scope)
        path = self._extract_path(request)

        # Create run name following convention: http:{method}:{path}
        run_name = f"http:{request.method}:{path}"

        # Build input metadata
        input_data = {
            "method": request.method,
            "path": str(request.url.path),
            "query_params": dict(request.query_params),
        }

        # Build run metadata
        metadata = {
            "http.method": request.method,
            "http.path": str(request.url.path),
            "http.client_host": request.client.host if request.client else None,
        }

        if self._capture_headers:
            metadata["http.user_agent"] = request.headers.get("user-agent")
            metadata["http.request_headers"] = dict(request.headers)

        # Track timing
        start_time = time.perf_counter()

        try:
            # Start the run using context manager
            # This automatically sets current_run() context variable
            with client.start_run(
                pipeline_name=run_name,
                input_data=input_data,
                metadata=metadata,
            ) as run:
                # Call the next middleware/handler
                response = await call_next(request)

                # Capture response metadata
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Update run metadata with response info
                run.metadata["http.status_code"] = response.status_code
                run.metadata["http.duration_ms"] = round(duration_ms, 2)

                if self._capture_headers and hasattr(response, "headers"):
                    run.metadata["http.response_headers"] = dict(response.headers)

                # Run ends automatically via context manager
                # Status will be 'success' since no exception was raised

                return response

        except Exception as e:
            # Exception occurred in application code
            # The context manager will automatically call run.end_with_error(e)
            # and then re-raise the exception
            # We just need to let it propagate
            raise

    def _extract_path(self, request: Request) -> str:
        """Extract the path template or raw path from the request.

        Args:
            request: The HTTP request

        Returns:
            Path template if available (e.g., "/users/{id}"),
            otherwise raw path (e.g., "/users/123")
        """
        if not self._path_template_extraction:
            return str(request.url.path)

        # FastAPI stores the matched route in request.scope["route"]
        # and the path template in request.scope["path"]
        scope = request.scope

        # Try to get route path template from FastAPI/Starlette
        if "route" in scope:
            route = scope["route"]
            if hasattr(route, "path"):
                # This is the template path like "/users/{user_id}"
                return route.path

        # Fallback to raw path
        return str(request.url.path)
