"""Tests for SDK transport layer."""

import asyncio

import httpx
import pytest
import respx

from sdk.config import XRayConfig
from sdk.transport import Transport


class TestTransportInit:
    """Tests for Transport initialization."""

    def test_creates_with_config(self) -> None:
        """Transport initializes with config."""
        config = XRayConfig(base_url="http://localhost:8000", buffer_size=100)
        transport = Transport(config)

        assert transport._config == config
        assert transport._batch_size == 100
        assert not transport.is_started

    def test_queue_size_matches_config(self) -> None:
        """Queue maxsize matches config buffer_size."""
        config = XRayConfig(buffer_size=50)
        transport = Transport(config)

        assert transport._queue.maxsize == 50


class TestTransportStart:
    """Tests for Transport.start()."""

    @pytest.mark.asyncio
    async def test_start_sets_started_flag(self) -> None:
        """Start sets is_started to True."""
        config = XRayConfig(base_url="http://localhost:8000")
        transport = Transport(config)

        await transport.start()
        assert transport.is_started

        await transport.shutdown()

    @pytest.mark.asyncio
    async def test_start_creates_client_when_base_url_set(self) -> None:
        """Start creates httpx client when base_url configured."""
        config = XRayConfig(base_url="http://localhost:8000")
        transport = Transport(config)

        await transport.start()
        assert transport._client is not None

        await transport.shutdown()

    @pytest.mark.asyncio
    async def test_start_no_client_without_base_url(self) -> None:
        """Start does not create client without base_url."""
        config = XRayConfig(base_url=None)
        transport = Transport(config)

        await transport.start()
        assert transport._client is None

        await transport.shutdown()

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self) -> None:
        """Calling start twice is safe."""
        config = XRayConfig(base_url="http://localhost:8000")
        transport = Transport(config)

        await transport.start()
        await transport.start()  # Should not raise
        assert transport.is_started

        await transport.shutdown()


class TestTransportSend:
    """Tests for Transport.send()."""

    @pytest.mark.asyncio
    async def test_send_queues_event(self) -> None:
        """Send adds event to queue."""
        config = XRayConfig(base_url="http://localhost:8000")
        transport = Transport(config)
        await transport.start()

        event = {"type": "step", "data": "test"}
        result = transport.send(event)

        assert result is True
        assert transport.queue_size == 1

        await transport.shutdown()

    @pytest.mark.asyncio
    async def test_send_before_start_returns_false(self) -> None:
        """Send returns False if transport not started."""
        config = XRayConfig(base_url="http://localhost:8000")
        transport = Transport(config)

        event = {"type": "step", "data": "test"}
        result = transport.send(event)

        assert result is False
        assert transport.queue_size == 0

    @pytest.mark.asyncio
    async def test_send_when_full_drops_event(self) -> None:
        """Send drops event when queue is full (fail-open)."""
        config = XRayConfig(base_url="http://localhost:8000", buffer_size=2)
        transport = Transport(config)
        await transport.start()

        # Fill the queue
        transport.send({"id": 1})
        transport.send({"id": 2})

        # This should drop
        result = transport.send({"id": 3})

        assert result is False
        assert transport.queue_size == 2

        await transport.shutdown()

    @pytest.mark.asyncio
    async def test_send_multiple_events(self) -> None:
        """Send multiple events to queue."""
        config = XRayConfig(base_url="http://localhost:8000", buffer_size=100)
        transport = Transport(config)
        await transport.start()

        for i in range(10):
            transport.send({"id": i})

        assert transport.queue_size == 10

        await transport.shutdown()


class TestTransportFlush:
    """Tests for Transport flush behavior."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_flush_sends_to_api(self, respx_mock: respx.MockRouter) -> None:
        """Flush sends events to API endpoint."""
        respx_mock.post("http://localhost:8000/ingest").respond(200)

        config = XRayConfig(
            base_url="http://localhost:8000", flush_interval=0.1, buffer_size=100
        )
        transport = Transport(config)
        await transport.start()

        transport.send({"type": "test"})

        # Wait for flush
        await asyncio.sleep(0.3)

        assert respx_mock.calls.call_count >= 1

        await transport.shutdown()

    @pytest.mark.asyncio
    @respx.mock
    async def test_flush_batches_events(self, respx_mock: respx.MockRouter) -> None:
        """Flush sends events in batches."""
        received_events: list = []

        def capture_request(request: httpx.Request) -> httpx.Response:
            import json

            received_events.extend(json.loads(request.content))
            return httpx.Response(200)

        respx_mock.post("http://localhost:8000/ingest").mock(side_effect=capture_request)

        config = XRayConfig(
            base_url="http://localhost:8000", flush_interval=0.1, buffer_size=100
        )
        transport = Transport(config)
        await transport.start()

        # Send multiple events
        for i in range(5):
            transport.send({"id": i})

        # Wait for flush
        await asyncio.sleep(0.3)

        assert len(received_events) == 5

        await transport.shutdown()

    @pytest.mark.asyncio
    @respx.mock
    async def test_flush_handles_network_error(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """Flush handles network errors gracefully (fail-open)."""
        respx_mock.post("http://localhost:8000/ingest").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        config = XRayConfig(
            base_url="http://localhost:8000", flush_interval=0.1, buffer_size=100
        )
        transport = Transport(config)
        await transport.start()

        transport.send({"type": "test"})

        # Wait for flush - should not raise
        await asyncio.sleep(0.3)

        # Transport should still be running
        assert transport.is_started

        await transport.shutdown()

    @pytest.mark.asyncio
    @respx.mock
    async def test_flush_handles_http_error(
        self, respx_mock: respx.MockRouter
    ) -> None:
        """Flush handles HTTP errors gracefully (fail-open)."""
        respx_mock.post("http://localhost:8000/ingest").respond(500)

        config = XRayConfig(
            base_url="http://localhost:8000", flush_interval=0.1, buffer_size=100
        )
        transport = Transport(config)
        await transport.start()

        transport.send({"type": "test"})

        # Wait for flush - should not raise
        await asyncio.sleep(0.3)

        # Transport should still be running
        assert transport.is_started

        await transport.shutdown()


class TestTransportShutdown:
    """Tests for Transport.shutdown()."""

    @pytest.mark.asyncio
    async def test_shutdown_sets_started_false(self) -> None:
        """Shutdown sets is_started to False."""
        config = XRayConfig(base_url="http://localhost:8000")
        transport = Transport(config)

        await transport.start()
        assert transport.is_started

        await transport.shutdown()
        assert not transport.is_started

    @pytest.mark.asyncio
    async def test_shutdown_closes_client(self) -> None:
        """Shutdown closes httpx client."""
        config = XRayConfig(base_url="http://localhost:8000")
        transport = Transport(config)

        await transport.start()
        assert transport._client is not None

        await transport.shutdown()
        assert transport._client is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_shutdown_drains_queue(self, respx_mock: respx.MockRouter) -> None:
        """Shutdown flushes remaining events in queue."""
        received_events: list = []

        def capture_request(request: httpx.Request) -> httpx.Response:
            import json

            received_events.extend(json.loads(request.content))
            return httpx.Response(200)

        respx_mock.post("http://localhost:8000/ingest").mock(side_effect=capture_request)

        config = XRayConfig(
            base_url="http://localhost:8000",
            flush_interval=10.0,  # Long interval so batch won't auto-flush
            buffer_size=100,
        )
        transport = Transport(config)
        await transport.start()

        # Send events
        for i in range(3):
            transport.send({"id": i})

        # Shutdown should flush remaining
        await transport.shutdown()

        assert len(received_events) == 3

    @pytest.mark.asyncio
    async def test_shutdown_is_idempotent(self) -> None:
        """Calling shutdown twice is safe."""
        config = XRayConfig(base_url="http://localhost:8000")
        transport = Transport(config)

        await transport.start()
        await transport.shutdown()
        await transport.shutdown()  # Should not raise

        assert not transport.is_started

    @pytest.mark.asyncio
    async def test_shutdown_without_start(self) -> None:
        """Shutdown without start is safe."""
        config = XRayConfig(base_url="http://localhost:8000")
        transport = Transport(config)

        await transport.shutdown()  # Should not raise
        assert not transport.is_started


class TestTransportHeaders:
    """Tests for Transport HTTP headers."""

    def test_headers_include_content_type(self) -> None:
        """Headers include Content-Type."""
        config = XRayConfig(base_url="http://localhost:8000")
        transport = Transport(config)

        headers = transport._get_headers()
        assert headers["Content-Type"] == "application/json"

    def test_headers_include_auth_when_api_key_set(self) -> None:
        """Headers include Authorization when api_key configured."""
        config = XRayConfig(base_url="http://localhost:8000", api_key="secret-key")
        transport = Transport(config)

        headers = transport._get_headers()
        assert headers["Authorization"] == "Bearer secret-key"

    def test_headers_no_auth_without_api_key(self) -> None:
        """Headers don't include Authorization without api_key."""
        config = XRayConfig(base_url="http://localhost:8000", api_key=None)
        transport = Transport(config)

        headers = transport._get_headers()
        assert "Authorization" not in headers
