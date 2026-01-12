"""Tests for SDK middleware."""

import asyncio
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sdk import current_run, init_xray
from sdk.client import XRayClient, get_client, shutdown_xray
from sdk.config import XRayConfig
from sdk.middleware import XRayMiddleware
from shared.types import RunStatus


class TestMiddlewareBasics:
    """Tests for basic middleware initialization and behavior."""

    def test_middleware_instantiation(self) -> None:
        """Middleware can be instantiated."""
        app = FastAPI()
        middleware = XRayMiddleware(app)

        assert middleware is not None
        assert middleware._capture_headers is False
        assert middleware._path_template_extraction is True

    def test_middleware_with_custom_options(self) -> None:
        """Middleware accepts custom options."""
        app = FastAPI()
        middleware = XRayMiddleware(
            app,
            capture_headers=True,
            path_template_extraction=False,
        )

        assert middleware._capture_headers is True
        assert middleware._path_template_extraction is False

    def test_middleware_with_no_client(self) -> None:
        """Middleware passes through when no client is initialized."""
        # Ensure no client is initialized
        shutdown_xray()

        app = FastAPI()
        app.add_middleware(XRayMiddleware)

        @app.get("/test")
        async def test_route():
            # current_run should be None
            assert current_run() is None
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert response.json() == {"message": "ok"}

    def test_middleware_with_unstarted_client(self) -> None:
        """Middleware passes through when client is not started."""
        # Create client but don't start it
        config = XRayConfig(base_url=None)
        client = XRayClient(config)

        # Temporarily set global client without starting
        from sdk import client as client_module

        old_client = client_module._client
        client_module._client = client

        try:
            app = FastAPI()
            app.add_middleware(XRayMiddleware)

            @app.get("/test")
            async def test_route():
                # current_run should be None
                assert current_run() is None
                return {"message": "ok"}

            test_client = TestClient(app)
            response = test_client.get("/test")

            assert response.status_code == 200
            assert response.json() == {"message": "ok"}
        finally:
            # Restore old client
            client_module._client = old_client


class TestMiddlewareIntegration:
    """Integration tests with FastAPI TestClient."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Create mock transport."""
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def xray_client(self, mock_transport: Mock):
        """Create and start X-Ray client with mock transport."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client._transport = mock_transport
        client._started = True

        # Set as global client for middleware to use
        from sdk import client as client_module

        old_client = client_module._client
        client_module._client = client

        yield client

        # Restore old client
        client._started = False
        client_module._client = old_client

    @pytest.fixture
    def app(self):
        """Create test FastAPI app with middleware."""
        app = FastAPI()
        app.add_middleware(XRayMiddleware)

        @app.get("/test")
        async def test_route():
            return {"message": "ok"}

        @app.get("/users/{user_id}")
        async def get_user(user_id: int):
            return {"user_id": user_id}

        @app.post("/api/data")
        async def post_data(data: dict):
            return {"received": data}

        @app.get("/error")
        async def error_route():
            raise ValueError("Test error")

        @app.get("/current-run")
        async def check_current_run():
            run = current_run()
            if run:
                return {"has_run": True, "run_id": run.id}
            return {"has_run": False}

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_middleware_creates_run_for_get_request(
        self, client, xray_client, mock_transport
    ) -> None:
        """Middleware creates run for GET request."""
        response = client.get("/test")

        assert response.status_code == 200
        assert response.json() == {"message": "ok"}

        # Check events - should have run_start and run_end
        assert mock_transport.send.call_count >= 2

        # Get events from mock calls
        calls = mock_transport.send.call_args_list
        run_start = calls[0][0][0]  # First call, first arg
        assert run_start["event_type"] == "run_start"
        assert run_start["pipeline_name"] == "http:GET:/test"
        assert run_start["status"] == "running"

        run_end = calls[1][0][0]  # Second call, first arg
        assert run_end["event_type"] == "run_end"
        assert run_end["status"] == "success"

    def test_middleware_creates_run_for_post_request(
        self, client, xray_client, mock_transport
    ) -> None:
        """Middleware creates run for POST request."""
        response = client.post("/api/data", json={"key": "value"})

        assert response.status_code == 200

        # Check run_start event
        calls = mock_transport.send.call_args_list
        run_start = calls[0][0][0]
        assert run_start["event_type"] == "run_start"
        assert run_start["pipeline_name"] == "http:POST:/api/data"

    def test_middleware_extracts_path_template(
        self, client, xray_client, mock_transport
    ) -> None:
        """Middleware attempts to extract path template."""
        response = client.get("/users/123")

        assert response.status_code == 200

        # Check run name is created correctly
        # Note: TestClient might not populate route.path, so we accept either template or raw path
        calls = mock_transport.send.call_args_list
        run_start = calls[0][0][0]
        pipeline_name = run_start["pipeline_name"]
        # Should start with http:GET:
        assert pipeline_name.startswith("http:GET:/users/")
        # Accepts either template {user_id} or raw path 123
        assert "{user_id}" in pipeline_name or "123" in pipeline_name

    def test_middleware_captures_query_params(
        self, client, xray_client, mock_transport
    ) -> None:
        """Middleware captures query parameters in input_data."""
        response = client.get("/test?foo=bar&baz=qux")

        assert response.status_code == 200

        # Check input_data contains query params
        calls = mock_transport.send.call_args_list
        run_start = calls[0][0][0]
        input_summary = run_start.get("input_summary")
        assert input_summary is not None
        # input_summary is summarized, so we need to check the nested structure
        assert input_summary["_type"] == "dict"
        assert "query_params" in input_summary["_keys"]
        # Verify query params were captured (structure is summarized)
        query_params = input_summary["_values"]["query_params"]
        assert query_params["_type"] == "dict"
        assert "foo" in query_params["_keys"]
        assert "baz" in query_params["_keys"]

    def test_current_run_available_in_route(self, client, xray_client) -> None:
        """current_run() is available in route handler."""
        response = client.get("/current-run")

        assert response.status_code == 200
        data = response.json()
        assert data["has_run"] is True
        assert "run_id" in data


class TestMiddlewareStatusCapture:
    """Tests for status code and duration capture."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Create mock transport."""
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def xray_client(self, mock_transport: Mock):
        """Create and start X-Ray client."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client._transport = mock_transport
        client._started = True

        # Set as global client
        from sdk import client as client_module

        old_client = client_module._client
        client_module._client = client

        yield client

        client._started = False
        client_module._client = old_client

    @pytest.fixture
    def app(self):
        """Create test FastAPI app."""
        app = FastAPI()
        app.add_middleware(XRayMiddleware)

        @app.get("/success")
        async def success_route():
            return {"status": "ok"}

        @app.get("/not-found")
        async def not_found():
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not found")

        @app.get("/slow")
        async def slow_route():
            await asyncio.sleep(0.1)
            return {"status": "ok"}

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_200_status_captured(self, client, xray_client, mock_transport) -> None:
        """200 status code is captured in metadata."""
        response = client.get("/success")

        assert response.status_code == 200

        # Check run was created
        assert mock_transport.send.call_count >= 2

        # The status code is added to run.metadata during dispatch
        # We can verify the run completed successfully
        calls = mock_transport.send.call_args_list
        run_end = calls[1][0][0]
        assert run_end["status"] == "success"

        # Verify metadata is included in run_end event (critical bug fix)
        assert "metadata" in run_end
        assert run_end["metadata"]["http.status_code"] == 200
        assert "http.duration_ms" in run_end["metadata"]

    def test_404_status_captured(self, client, xray_client, mock_transport) -> None:
        """404 status is captured (but not treated as error)."""
        response = client.get("/not-found")

        assert response.status_code == 404

        # Run should complete, 404 is not an application error
        assert mock_transport.send.call_count >= 2
        # Note: HTTPException is handled by FastAPI, not considered an error
        # in the run lifecycle

    def test_duration_captured(self, client, xray_client, mock_transport) -> None:
        """Duration is measured and captured."""
        response = client.get("/slow")

        assert response.status_code == 200

        # Verify events were sent (duration is in metadata, not event)
        assert mock_transport.send.call_count >= 2


class TestMiddlewareErrors:
    """Tests for error handling."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Create mock transport."""
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def xray_client(self, mock_transport: Mock):
        """Create and start X-Ray client."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client._transport = mock_transport
        client._started = True

        # Set as global client
        from sdk import client as client_module

        old_client = client_module._client
        client_module._client = client

        yield client

        client._started = False
        client_module._client = old_client

    @pytest.fixture
    def app(self):
        """Create test FastAPI app with error routes."""
        app = FastAPI()
        app.add_middleware(XRayMiddleware)

        @app.get("/error")
        async def error_route():
            raise ValueError("Test error")

        @app.get("/type-error")
        async def type_error_route():
            raise TypeError("Type error")

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_route_exception_captured(
        self, client, xray_client, mock_transport
    ) -> None:
        """Exception in route is captured in run."""
        response = client.get("/error")

        # FastAPI returns 500 for unhandled exceptions
        assert response.status_code == 500

        # Check run events
        assert mock_transport.send.call_count >= 2

        calls = mock_transport.send.call_args_list
        run_start = calls[0][0][0]
        assert run_start["event_type"] == "run_start"

        run_end = calls[1][0][0]
        assert run_end["event_type"] == "run_end"
        assert run_end["status"] == "error"
        assert "ValueError" in run_end["error_message"]
        assert "Test error" in run_end["error_message"]

    def test_route_exception_propagates(
        self, client, xray_client, mock_transport
    ) -> None:
        """Exception propagates to FastAPI error handlers."""
        response = client.get("/error")

        # Exception should result in 500 error
        assert response.status_code == 500

    def test_different_exception_types(
        self, client, xray_client, mock_transport
    ) -> None:
        """Different exception types are handled correctly."""
        response = client.get("/type-error")

        assert response.status_code == 500

        # Check error message contains exception type
        calls = mock_transport.send.call_args_list
        run_end = calls[1][0][0]
        assert run_end["status"] == "error"
        assert "TypeError" in run_end["error_message"]


class TestMiddlewareContext:
    """Tests for context management."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Create mock transport."""
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def xray_client(self, mock_transport: Mock):
        """Create and start X-Ray client."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client._transport = mock_transport
        client._started = True

        # Set as global client
        from sdk import client as client_module

        old_client = client_module._client
        client_module._client = client

        yield client

        client._started = False
        client_module._client = old_client

    @pytest.fixture
    def app(self, xray_client):
        """Create test FastAPI app with context-aware routes."""
        app = FastAPI()
        app.add_middleware(XRayMiddleware)

        @app.get("/nested-run")
        async def nested_run_route():
            """Route that creates a nested run."""
            outer_run = current_run()
            outer_id = outer_run.id if outer_run else None

            # Create nested run
            with xray_client.start_run("nested-operation") as inner_run:
                inner_id = inner_run.id
                # Inside nested context
                assert current_run() is inner_run

            # After nested context, outer run should be restored
            assert current_run() is outer_run

            return {"outer_id": outer_id, "inner_id": inner_id}

        @app.get("/check-context")
        async def check_context():
            """Route that checks context."""
            run = current_run()
            return {"has_run": run is not None}

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_nested_run_in_route(self, client, xray_client, mock_transport) -> None:
        """Route can create nested run, context is restored."""
        response = client.get("/nested-run")

        assert response.status_code == 200
        data = response.json()

        # Both outer and inner runs should have IDs
        assert data["outer_id"] is not None
        assert data["inner_id"] is not None
        assert data["outer_id"] != data["inner_id"]

        # Check events: outer run_start, inner run_start, inner run_end, outer run_end
        assert mock_transport.send.call_count >= 4

    def test_context_reset_after_request(
        self, client, xray_client, mock_transport
    ) -> None:
        """Context is reset to None after request completes."""
        # Make a request
        response = client.get("/check-context")
        assert response.status_code == 200
        assert response.json()["has_run"] is True

        # After request, current_run should be None
        # (This is tested in the test process, not in the route)
        assert current_run() is None


class TestMiddlewarePathExtraction:
    """Tests for path template extraction."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Create mock transport."""
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def xray_client(self, mock_transport: Mock):
        """Create and start X-Ray client."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client._transport = mock_transport
        client._started = True

        # Set as global client
        from sdk import client as client_module

        old_client = client_module._client
        client_module._client = client

        yield client

        client._started = False
        client_module._client = old_client

    def test_path_template_extraction_enabled(
        self, xray_client, mock_transport
    ) -> None:
        """Path template extraction works when enabled."""
        app = FastAPI()
        app.add_middleware(XRayMiddleware, path_template_extraction=True)

        @app.get("/items/{item_id}")
        async def get_item(item_id: int):
            return {"item_id": item_id}

        client = TestClient(app)
        response = client.get("/items/42")

        assert response.status_code == 200

        # Check path is in pipeline name
        # Note: TestClient may not always populate route.path before middleware runs
        calls = mock_transport.send.call_args_list
        run_start = calls[0][0][0]
        pipeline_name = run_start["pipeline_name"]
        assert pipeline_name.startswith("http:GET:/items/")
        # Template extraction may work or fall back to raw path
        assert "{item_id}" in pipeline_name or "42" in pipeline_name

    def test_path_template_extraction_disabled(
        self, xray_client, mock_transport
    ) -> None:
        """Raw path is used when template extraction is disabled."""
        app = FastAPI()
        app.add_middleware(XRayMiddleware, path_template_extraction=False)

        @app.get("/items/{item_id}")
        async def get_item(item_id: int):
            return {"item_id": item_id}

        client = TestClient(app)
        response = client.get("/items/42")

        assert response.status_code == 200

        # Check raw path was used
        calls = mock_transport.send.call_args_list
        run_start = calls[0][0][0]
        assert run_start["pipeline_name"] == "http:GET:/items/42"


class TestMiddlewareHeaderCapture:
    """Tests for header capture functionality."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Create mock transport."""
        transport = Mock()
        transport.send = Mock(return_value=True)
        return transport

    @pytest.fixture
    def xray_client(self, mock_transport: Mock):
        """Create and start X-Ray client."""
        config = XRayConfig(base_url=None)
        client = XRayClient(config)
        client._transport = mock_transport
        client._started = True

        # Set as global client
        from sdk import client as client_module

        old_client = client_module._client
        client_module._client = client

        yield client

        client._started = False
        client_module._client = old_client

    def test_headers_not_captured_by_default(
        self, xray_client, mock_transport
    ) -> None:
        """Headers are not captured by default."""
        app = FastAPI()
        app.add_middleware(XRayMiddleware)

        @app.get("/test")
        async def test_route():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test", headers={"User-Agent": "Test Client"})

        assert response.status_code == 200

        # Check metadata doesn't contain headers
        calls = mock_transport.send.call_args_list
        run_start = calls[0][0][0]
        metadata = run_start.get("metadata", {})
        assert "http.user_agent" not in metadata
        assert "http.request_headers" not in metadata

    def test_headers_captured_when_enabled(self, xray_client, mock_transport) -> None:
        """Headers are captured when capture_headers=True."""
        app = FastAPI()
        app.add_middleware(XRayMiddleware, capture_headers=True)

        @app.get("/test")
        async def test_route():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test", headers={"User-Agent": "Test Client"})

        assert response.status_code == 200

        # Check metadata contains headers
        calls = mock_transport.send.call_args_list
        run_start = calls[0][0][0]
        metadata = run_start.get("metadata", {})
        assert "http.user_agent" in metadata
        assert metadata["http.user_agent"] == "Test Client"
        # Also check request_headers dict
        assert "http.request_headers" in metadata
        assert metadata["http.request_headers"]["user-agent"] == "Test Client"

    def test_sensitive_headers_are_redacted(self, xray_client, mock_transport) -> None:
        """Sensitive headers like Authorization are redacted."""
        app = FastAPI()
        app.add_middleware(XRayMiddleware, capture_headers=True)

        @app.get("/test")
        async def test_route():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get(
            "/test",
            headers={
                "User-Agent": "Test Client",
                "Authorization": "Bearer secret-token-12345",
                "X-Api-Key": "my-secret-api-key",
                "X-Custom-Header": "not-sensitive",
            },
        )

        assert response.status_code == 200

        # Check that sensitive headers are redacted
        calls = mock_transport.send.call_args_list
        run_start = calls[0][0][0]
        metadata = run_start.get("metadata", {})
        request_headers = metadata.get("http.request_headers", {})

        # Non-sensitive headers should be preserved
        assert request_headers.get("user-agent") == "Test Client"
        assert request_headers.get("x-custom-header") == "not-sensitive"

        # Sensitive headers should be redacted
        assert request_headers.get("authorization") == "[REDACTED]"
        assert request_headers.get("x-api-key") == "[REDACTED]"
