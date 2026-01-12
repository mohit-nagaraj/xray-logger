"""Authentication dependencies for X-Ray API.

Provides optional API key authentication via environment variable:
- XRAY_API_KEY: The API key that clients must provide

If XRAY_API_KEY is not set, authentication is disabled.
If XRAY_API_KEY is set, authentication is enabled and required.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.config import APIConfig, load_config

# HTTP Bearer scheme for automatic Authorization header parsing
# auto_error=False prevents automatic 403 response, allowing custom error handling
security = HTTPBearer(auto_error=False)


def get_config() -> APIConfig:
    """Get current API configuration.

    This function is used as a dependency to provide config to other dependencies.
    """
    return load_config()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    config: APIConfig = Depends(get_config),
) -> None:
    """Verify API key from Authorization header.

    This dependency function implements optional API key authentication:
    1. If config.api_key is not set, returns immediately (auth disabled)
    2. If config.api_key is set, validates Authorization: Bearer {token}
    3. Raises 401 Unauthorized if authentication fails

    The dependency should be added to routes that need protection:
        @router.post("/ingest", dependencies=[Depends(verify_api_key)])
        async def ingest_events(...):
            ...

    Args:
        credentials: HTTP Authorization credentials (Bearer token) from request
        config: API configuration containing api_key setting

    Raises:
        HTTPException: 401 if authentication enabled but credentials invalid/missing
    """
    # If API key not configured, authentication is disabled
    if not config.api_key:
        return

    # Authentication is enabled from this point

    # Check if Authorization header was provided
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate token matches configured API key
    if credentials.credentials != config.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Authentication successful - allow request through
    return
