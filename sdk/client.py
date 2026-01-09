"""X-Ray SDK client with context management.

This module provides the main entry point for instrumenting pipelines with X-Ray.
It uses contextvars for async-safe context propagation and manages the transport
lifecycle via a background thread.

Architecture:
    - XRayClient: Main client class that holds Transport and provides start_run()
    - Context Variables: _current_run tracks active Run per async context
    - Background Thread: Runs asyncio event loop for async Transport
    - Global Functions: init_xray(), current_run(), current_step(), etc.

Example:
    from sdk import init_xray, current_run
    from sdk.config import XRayConfig

    # Initialize once at startup
    client = init_xray(XRayConfig(base_url="http://localhost:8000"))

    # Use context manager for runs
    with client.start_run("my_pipeline", input_data={"query": "test"}) as run:
        step = run.start_step("filter", "filter", candidates)
        # ... do work ...
        step.end(filtered_candidates)

    # Access current run from anywhere in the call stack
    run = current_run()  # Returns active Run or None
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import threading
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any, Generator

from .config import XRayConfig, load_config
from .run import Run
from .transport import Transport

if TYPE_CHECKING:
    from .step import Step

logger = logging.getLogger(__name__)

# Context variable for tracking active run
# Uses contextvars for proper async isolation - each async task gets its own copy
_current_run: ContextVar[Run | None] = ContextVar("xray_current_run", default=None)

# Global client singleton
_client: XRayClient | None = None


class XRayClient:
    """X-Ray SDK client for instrumenting pipelines.

    This client manages the Transport lifecycle and provides context management
    for tracking active Runs. It uses a background thread with its own event loop
    to bridge the async Transport with synchronous client code.

    Lifecycle:
        1. Create client with config
        2. Call start() to initialize background transport
        3. Use start_run() context manager for pipeline instrumentation
        4. Call shutdown() for graceful cleanup (or rely on atexit handler)

    Thread Safety:
        - The client is thread-safe for concurrent start_run() calls
        - Context variables provide isolation between async tasks
        - Transport uses thread-safe queue for event buffering

    Example:
        client = XRayClient(XRayConfig(base_url="http://localhost:8000"))
        client.start()

        with client.start_run("pipeline") as run:
            step = run.start_step("process", "transform", data)
            result = process(data)
            step.end(result)

        client.shutdown()
    """

    def __init__(self, config: XRayConfig) -> None:
        """Initialize the X-Ray client.

        Args:
            config: SDK configuration including base_url, api_key, buffer settings
        """
        self._config = config
        self._transport = Transport(config)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = False
        self._shutdown_registered = False

    @property
    def is_started(self) -> bool:
        """Check if the client is started and ready to accept events."""
        return self._started

    @property
    def config(self) -> XRayConfig:
        """Get the client configuration."""
        return self._config

    def start(self) -> None:
        """Start the client and initialize background transport.

        Creates a background thread with its own asyncio event loop to run
        the async Transport. This allows the SDK to work in both sync and
        async Python code without blocking.

        This method is idempotent - calling it multiple times is safe.

        Raises:
            No exceptions - fails open with warning log if transport fails to start.
        """
        if self._started:
            return

        # Create background thread with event loop for async transport
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,  # Won't block process exit
            name="xray-transport",
        )
        self._thread.start()

        # Start transport in background loop
        future = asyncio.run_coroutine_threadsafe(self._transport.start(), self._loop)
        try:
            future.result(timeout=5.0)
        except Exception as e:
            logger.warning("Failed to start X-Ray transport: %s", e)
            # Fail open - client will still work but events won't be sent
            return

        self._started = True

        # Register atexit handler for graceful shutdown
        if not self._shutdown_registered:
            atexit.register(self._atexit_shutdown)
            self._shutdown_registered = True

        logger.debug("X-Ray client started")

    def _run_loop(self) -> None:
        """Run the asyncio event loop in background thread."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _atexit_shutdown(self) -> None:
        """Shutdown handler registered with atexit.

        Uses shorter timeout to avoid blocking process exit.
        """
        self.shutdown(timeout=2.0)

    def shutdown(self, timeout: float = 5.0) -> None:
        """Shutdown the client gracefully.

        Flushes remaining events in the transport buffer and stops the
        background thread. This method is idempotent.

        Args:
            timeout: Maximum seconds to wait for shutdown to complete.
        """
        if not self._started:
            return

        self._started = False
        logger.debug("Shutting down X-Ray client")

        if self._loop and self._thread:
            # Shutdown transport (flushes remaining events)
            future = asyncio.run_coroutine_threadsafe(
                self._transport.shutdown(timeout), self._loop
            )
            try:
                future.result(timeout=timeout)
            except Exception as e:
                logger.warning("Error during X-Ray transport shutdown: %s", e)

            # Stop event loop and join thread
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=timeout)

            self._loop = None
            self._thread = None

        logger.debug("X-Ray client shutdown complete")

    @contextmanager
    def start_run(
        self,
        pipeline_name: str,
        input_data: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> Generator[Run, None, None]:
        """Start a new Run as a context manager.

        Creates a Run, sets it as the current run in the context variable,
        and automatically ends it when the context exits. Properly handles
        exceptions by marking the run as error.

        The context variable token is saved and restored on exit, enabling
        nested runs where inner runs don't affect outer run context.

        Args:
            pipeline_name: Name of the pipeline (e.g., "recommendation_pipeline")
            input_data: Optional input data to summarize
            metadata: Optional metadata (request_id, user_id, environment, etc.)

        Yields:
            Run instance for creating steps

        Example:
            with client.start_run("my_pipeline", metadata={"user_id": "123"}) as run:
                step = run.start_step("filter", "filter", candidates)
                filtered = filter_candidates(candidates)
                step.end(filtered)
        """
        run = Run(
            self._transport,
            pipeline_name,
            input_data=input_data,
            metadata=metadata,
        )

        # Set context variable and save token for proper reset
        token: Token[Run | None] = _current_run.set(run)

        try:
            yield run
        except BaseException as e:
            # Mark run as error if not already ended
            if run._ended_at is None:
                run.end_with_error(e)
            raise
        finally:
            # Reset context variable to previous value (supports nesting)
            _current_run.reset(token)
            # End run if not already ended
            if run._ended_at is None:
                run.end()


# --- Global Functions ---


def init_xray(config: XRayConfig | None = None) -> XRayClient:
    """Initialize the global X-Ray client.

    Creates and starts the global client singleton. This should be called
    once at application startup. Subsequent calls will replace the existing
    client.

    Args:
        config: SDK configuration. If None, loads from xray.config.yaml.

    Returns:
        The initialized XRayClient instance.

    Example:
        # With explicit config
        init_xray(XRayConfig(base_url="http://localhost:8000"))

        # With config file
        init_xray()  # Loads from xray.config.yaml
    """
    global _client

    if config is None:
        config = load_config()

    _client = XRayClient(config)
    _client.start()

    return _client


def get_client() -> XRayClient | None:
    """Get the global X-Ray client.

    Returns:
        The global XRayClient instance, or None if not initialized.
    """
    return _client


def current_run() -> Run | None:
    """Get the current active Run.

    Uses contextvars to retrieve the Run for the current execution context.
    This properly handles async code where multiple tasks may have different
    active runs.

    Returns:
        The current Run, or None if no run is active.

    Example:
        with client.start_run("pipeline") as run:
            # Inside the context
            assert current_run() is run

        # Outside the context
        assert current_run() is None
    """
    return _current_run.get()


def current_step() -> Step | None:
    """Get the current active Step.

    Returns the most recently started step that hasn't ended yet from the
    current run. This is useful in decorated functions or helpers that need
    to attach reasoning to the current step.

    Returns:
        The current active Step, or None if no step is active.

    Example:
        with client.start_run("pipeline") as run:
            step = run.start_step("process", "transform", data)
            # Inside the step
            assert current_step() is step

            step.end(result)
            # After step ends
            assert current_step() is None
    """
    run = _current_run.get()
    if run is None:
        return None

    # Return last non-ended step (most recently started active step)
    for step in reversed(run._steps):
        if step._ended_at is None:
            return step

    return None


def shutdown_xray(timeout: float = 5.0) -> None:
    """Shutdown the global X-Ray client.

    Gracefully shuts down the client, flushing any remaining events.
    After calling this, init_xray() must be called again to use the SDK.

    Args:
        timeout: Maximum seconds to wait for shutdown to complete.
    """
    global _client

    if _client is not None:
        _client.shutdown(timeout)
        _client = None
