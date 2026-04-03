"""Tests for OAuth2 token management."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from google_home_blade_mcp.auth import TokenManager
from google_home_blade_mcp.models import AuthError


class TestTokenManager:
    def test_starts_expired(self) -> None:
        tm = TokenManager("cid", "csec", "rtok")
        assert tm.is_expired is True

    def test_refresh_success(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "ya29.new_token", "expires_in": 3600}
        mock_response.raise_for_status = MagicMock()

        with patch("google_home_blade_mcp.auth.httpx.post", return_value=mock_response):
            tm = TokenManager("cid", "csec", "rtok")
            token = tm.get_access_token()
            assert token == "ya29.new_token"
            assert tm.is_expired is False

    def test_refresh_http_error(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=mock_response
        )

        with patch("google_home_blade_mcp.auth.httpx.post", return_value=mock_response):
            tm = TokenManager("cid", "csec", "rtok")
            with pytest.raises(AuthError, match="Token refresh failed"):
                tm.get_access_token()

    def test_invalidate(self) -> None:
        tm = TokenManager("cid", "csec", "rtok")
        tm._access_token = "old"
        tm._expires_at = time.time() + 3600
        assert tm.is_expired is False

        tm.invalidate()
        assert tm.is_expired is True

    def test_skips_refresh_when_valid(self) -> None:
        tm = TokenManager("cid", "csec", "rtok")
        tm._access_token = "valid_token"
        tm._expires_at = time.time() + 3600

        with patch("google_home_blade_mcp.auth.httpx.post") as mock_post:
            token = tm.get_access_token()
            assert token == "valid_token"
            mock_post.assert_not_called()

    def test_refreshes_when_near_expiry(self) -> None:
        """Token refresh happens when within 60s of expiry."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "ya29.fresh", "expires_in": 3600}
        mock_response.raise_for_status = MagicMock()

        tm = TokenManager("cid", "csec", "rtok")
        tm._access_token = "stale"
        tm._expires_at = time.time() + 30  # 30s left, within 60s buffer

        with patch("google_home_blade_mcp.auth.httpx.post", return_value=mock_response):
            token = tm.get_access_token()
            assert token == "ya29.fresh"
