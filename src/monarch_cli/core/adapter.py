"""Adapter module to isolate upstream library details.

All monarchmoney imports are centralized here. This protects the rest of
the codebase from upstream library changes.
"""

from __future__ import annotations

from typing import cast

from monarchmoney import MonarchMoney  # type: ignore[import-untyped]

from .exceptions import AuthenticationError
from .session import get_session_token

# Module-level cached client instance
_client: MonarchMoney | None = None


def get_authenticated_client() -> MonarchMoney:
    """Get an authenticated MonarchMoney client instance.

    Uses cached instance if available. Token is retrieved from session storage.

    Returns:
        MonarchMoney: Authenticated client instance.

    Raises:
        AuthenticationError: If no token is available.
    """
    global _client

    if _client is not None:
        return _client

    token = get_session_token()
    if token is None:
        raise AuthenticationError()

    # Use constructor parameter, never manipulate private attributes
    _client = MonarchMoney(token=token)
    return _client


def extract_token_from_client(client: MonarchMoney) -> str | None:
    """Extract the token from a MonarchMoney client instance.

    Args:
        client: The MonarchMoney client instance.

    Returns:
        The token string if set, None otherwise.
    """
    token = client.token
    return cast(str, token) if token is not None else None


def reset_client() -> None:
    """Clear the cached client instance.

    Call this on logout to ensure next authentication uses fresh credentials.
    """
    global _client
    _client = None
