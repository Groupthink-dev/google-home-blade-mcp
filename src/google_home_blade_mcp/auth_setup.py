"""Interactive OAuth2 setup for Google Home Blade MCP.

Run via: make auth
    or: python -m google_home_blade_mcp.auth_setup

Opens browser for Google consent, catches callback on localhost,
exchanges code for refresh token, and prints it for env var storage.
"""

from __future__ import annotations

import http.server
import os
import sys
import threading
import urllib.parse
import webbrowser

import httpx

from google_home_blade_mcp.models import GOOGLE_TOKEN_URL, SDM_SCOPE

REDIRECT_PORT = 9876
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"


def _build_auth_url(client_id: str, project_id: str) -> str:
    """Build the Google OAuth2 authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SDM_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"https://nestservices.google.com/partnerconnections/{project_id}/auth?" + urllib.parse.urlencode(params)


def _exchange_code(client_id: str, client_secret: str, code: str) -> dict[str, str]:
    """Exchange authorization code for tokens."""
    resp = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that catches the OAuth callback."""

    auth_code: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        code = params.get("code", [None])[0]

        if code:
            _CallbackHandler.auth_code = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Authorization successful!</h2><p>You can close this tab.</p>")
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<h2>Authorization failed: {error}</h2>".encode())

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # Suppress request logging


def main() -> None:
    """Run the interactive OAuth2 setup flow."""
    client_id = os.environ.get("GOOGLE_HOME_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_HOME_CLIENT_SECRET", "")
    project_id = os.environ.get("GOOGLE_HOME_PROJECT_ID", "")

    if not client_id or not client_secret or not project_id:
        print("Error: Set these environment variables first:")
        print("  GOOGLE_HOME_CLIENT_ID     — OAuth2 client ID from GCP Console")
        print("  GOOGLE_HOME_CLIENT_SECRET — OAuth2 client secret from GCP Console")
        print("  GOOGLE_HOME_PROJECT_ID    — Project ID from Device Access Console")
        sys.exit(1)

    auth_url = _build_auth_url(client_id, project_id)

    print("\n=== Google Home Blade MCP — OAuth2 Setup ===\n")
    print("Opening browser for Google authorization...")
    print(f"If it doesn't open, visit:\n  {auth_url}\n")

    server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    webbrowser.open(auth_url)

    print("Waiting for authorization callback...")
    server_thread.join(timeout=120)
    server.server_close()

    if not _CallbackHandler.auth_code:
        print("\nError: No authorization code received (timeout or denied).")
        sys.exit(1)

    print("Exchanging code for tokens...")
    try:
        tokens = _exchange_code(client_id, client_secret, _CallbackHandler.auth_code)
    except httpx.HTTPStatusError as e:
        print(f"\nError: Token exchange failed ({e.response.status_code})")
        sys.exit(1)

    refresh_token = tokens.get("refresh_token", "")
    if not refresh_token:
        print("\nError: No refresh token in response. Try again with prompt=consent.")
        sys.exit(1)

    print("\n=== Setup Complete ===\n")
    print("Add this to your environment:\n")
    print(f'  GOOGLE_HOME_REFRESH_TOKEN="{refresh_token}"\n')
    print("Keep this token secret. It provides access to your Google Home devices.")


if __name__ == "__main__":
    main()
