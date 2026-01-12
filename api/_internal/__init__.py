"""Internal implementation modules for X-Ray API.

This package contains private implementation details that should not be
imported directly by users. Use the public API from the api package instead.

Modules:
    database: Database engine and session management
    store: Data access layer for Run and Step CRUD operations
"""

# Import store as a module for backwards compatibility
from . import store

# Export database functions
from .database import close_db, get_session, init_db, is_initialized

# Export store functions for direct import
from .store import (
    count_runs,
    count_steps,
    create_payloads,
    create_run,
    create_step,
    end_run,
    end_step,
    get_payloads,
    get_run,
    get_step,
    list_runs,
    list_steps,
)

__all__ = [
    # Submodules
    "store",
    # Database
    "init_db",
    "get_session",
    "close_db",
    "is_initialized",
    # Store functions
    "create_run",
    "end_run",
    "create_step",
    "end_step",
    "get_run",
    "get_step",
    "list_runs",
    "list_steps",
    "count_runs",
    "count_steps",
    "create_payloads",
    "get_payloads",
]
