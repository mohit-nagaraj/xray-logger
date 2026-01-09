"""Async buffered transport for sending events to X-Ray API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import XRayConfig

logger = logging.getLogger(__name__)


class Transport:
    """Async buffered transport with fail-open semantics.

    Events are queued and sent in batches to minimize overhead.
    If the queue is full, events are dropped (fail-open).
    Network errors are logged but never crash the application.
    """

    def __init__(self, config: XRayConfig) -> None:
        self._config = config
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=config.buffer_size
        )
        self._client: httpx.AsyncClient | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._shutdown = asyncio.Event()
        self._started = False
        self._batch_size = config.batch_size

    @property
    def is_started(self) -> bool:
        """Check if transport is started."""
        return self._started

    @property
    def queue_size(self) -> int:
        """Current number of events in queue."""
        return self._queue.qsize()

    async def start(self) -> None:
        """Start the background worker."""
        if self._started:
            return

        if self._config.base_url:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url,
                headers=self._get_headers(),
                timeout=self._config.http_timeout,
            )

        self._shutdown.clear()
        self._worker_task = asyncio.create_task(self._worker_loop())
        self._started = True
        logger.debug("Transport started")

    def send(self, event: dict[str, Any]) -> bool:
        """Queue event for sending. Non-blocking, fail-open.

        Args:
            event: Event data to send.

        Returns:
            True if event was queued, False if dropped.
        """
        if not self._started:
            logger.debug("Transport not started, dropping event")
            return False

        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            logger.warning("Event buffer full, dropping event")
            return False

    async def _worker_loop(self) -> None:
        """Background worker that batches and flushes events."""
        while not self._shutdown.is_set():
            try:
                batch = await self._collect_batch()
                if batch:
                    await self._flush_batch(batch)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("Worker loop error: %s", e)
                await asyncio.sleep(1.0)

    async def _collect_batch(self) -> list[dict[str, Any]]:
        """Collect events into a batch with timeout."""
        batch: list[dict[str, Any]] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._config.flush_interval

        while len(batch) < self._batch_size:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break

            try:
                event = await asyncio.wait_for(
                    self._queue.get(), timeout=max(0.1, remaining)
                )
                batch.append(event)
            except asyncio.TimeoutError:
                break

        return batch

    async def _flush_batch(self, events: list[dict[str, Any]]) -> None:
        """Send batch of events to API."""
        if not self._client or not self._config.base_url:
            logger.debug("No API configured, discarding %d events", len(events))
            return

        try:
            response = await self._client.post("/ingest", json=events)
            response.raise_for_status()
            logger.debug("Flushed %d events", len(events))
        except httpx.RequestError as e:
            logger.warning("Network error sending events: %s", e)
        except httpx.HTTPStatusError as e:
            logger.warning(
                "HTTP %d error sending events: %s", e.response.status_code, e
            )

    async def shutdown(self, timeout: float = 5.0) -> None:
        """Gracefully shutdown, attempting to flush remaining events.

        Args:
            timeout: Max seconds to wait for worker to finish.
        """
        if not self._started:
            return

        logger.debug("Shutting down transport")
        self._shutdown.set()

        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=timeout)
            except asyncio.TimeoutError:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass

        # Stop accepting new events before the final drain to prevent race condition
        self._started = False

        remaining: list[dict[str, Any]] = []
        while not self._queue.empty():
            try:
                remaining.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if remaining:
            logger.debug("Flushing %d remaining events", len(remaining))
            try:
                await self._flush_batch(remaining)
            except Exception as e:
                logger.warning("Error flushing remaining events during shutdown: %s", e)

        if self._client:
            await self._client.aclose()
            self._client = None

        logger.debug("Transport shutdown complete")

    def _get_headers(self) -> dict[str, str]:
        """Build HTTP headers including auth if configured."""
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        return headers
