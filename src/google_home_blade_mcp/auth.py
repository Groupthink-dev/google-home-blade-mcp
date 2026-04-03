"""OAuth2 token management for SDM API.

Handles access token refresh using the stored refresh token.
Access tokens are kept in memory only — never written to disk.
"""

from __future__ import annotations

import logging
import time

import httpx

from google_home_blade_mcp.models import (
    GOOGLE_TOKEN_URL,
    AuthError,
    _scrub_credentials,
)

logger = logging.getLogger(__name__)


class TokenManager:
    """Manages OAuth2 access tokens with automatic refresh.

    Thread-safe for use with asyncio.to_thread — refresh is
    synchronous and guarded by expiry check.
    """

    def __init__(self, client_id: str, client_secret: str, refresh_token: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    @property
    def is_expired(self) -> bool:
        """Check if access token is expired or about to expire (60s buffer)."""
        return self._access_token is None or time.time() >= (self._expires_at - 60)

    def get_access_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        if self.is_expired:
            self._refresh()
        assert self._access_token is not None  # noqa: S101
        return self._access_token

    def _refresh(self) -> None:
        """Exchange refresh token for a new access token."""
        try:
            response = httpx.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            self._access_token = data["access_token"]
            self._expires_at = time.time() + int(data.get("expires_in", 3600))
            logger.debug("Access token refreshed, expires in %ss", data.get("expires_in", 3600))

        except httpx.HTTPStatusError as e:
            body = _scrub_credentials(e.response.text)
            raise AuthError(f"Token refresh failed ({e.response.status_code}): {body}") from e
        except httpx.HTTPError as e:
            raise AuthError(f"Token refresh failed: {_scrub_credentials(str(e))}") from e
        except KeyError as e:
            raise AuthError(f"Token response missing field: {e}") from e

    def invalidate(self) -> None:
        """Force token refresh on next access."""
        self._access_token = None
        self._expires_at = 0.0


class BearerAuthMiddleware:
    """ASGI middleware for optional bearer token auth on HTTP transport."""

    def __init__(self, app: object) -> None:
        self.app = app  # type: ignore[assignment]

    async def __call__(self, scope: dict[str, object], receive: object, send: object) -> None:
        import os

        expected = os.environ.get("GOOGLE_HOME_MCP_API_TOKEN")
        if expected is None:
            await self.app(scope, receive, send)  # type: ignore[misc]
            return

        if scope.get("type") != "http":
            await self.app(scope, receive, send)  # type: ignore[misc]
            return

        headers = dict(scope.get("headers", []))  # type: ignore[arg-type]
        auth = headers.get(b"authorization", b"").decode()

        if auth == f"Bearer {expected}":
            await self.app(scope, receive, send)  # type: ignore[misc]
            return

        async def send_401(message: dict[str, object]) -> None:
            pass

        await send(  # type: ignore[misc]
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [[b"content-type", b"text/plain"]],
            }
        )
        await send({"type": "http.response.body", "body": b"Unauthorized"})  # type: ignore[misc]
