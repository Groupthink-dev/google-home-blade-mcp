"""SDM API client for Google Home / Nest devices.

Synchronous methods wrapped by asyncio.to_thread in server.py.
All errors are classified into typed exceptions with credential scrubbing.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from google_home_blade_mcp.auth import TokenManager
from google_home_blade_mcp.models import (
    SDM_BASE_URL,
    AuthError,
    DeviceInfo,
    GoogleHomeConfig,
    GoogleHomeError,
    RoomInfo,
    StructureInfo,
    _scrub_credentials,
    classify_error,
)

logger = logging.getLogger(__name__)


class GoogleHomeClient:
    """Client for the Google Smart Device Management (SDM) API.

    Handles authentication, request/response, and error classification.
    """

    def __init__(self, config: GoogleHomeConfig | None = None) -> None:
        if config is None:
            config = GoogleHomeConfig.from_env()
        self._config = config
        self._token_manager = TokenManager(
            client_id=config.client_id,
            client_secret=config.client_secret,
            refresh_token=config.refresh_token,
        )
        self._http = httpx.Client(timeout=15.0)
        self._base = f"{SDM_BASE_URL}/enterprises/{config.project_id}"

    def close(self) -> None:
        """Close the HTTP client."""
        self._http.close()

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Build request headers with fresh access token."""
        return {
            "Authorization": f"Bearer {self._token_manager.get_access_token()}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> dict[str, Any]:
        """GET request to SDM API."""
        url = f"{self._base}{path}"
        try:
            resp = self._http.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                self._token_manager.invalidate()
            raise classify_error(_scrub_credentials(f"{e.response.status_code}: {e.response.text}")) from e
        except httpx.HTTPError as e:
            raise GoogleHomeError(_scrub_credentials(str(e))) from e

    def _post(self, path: str, json_body: dict[str, Any]) -> dict[str, Any]:
        """POST request to SDM API."""
        url = f"{self._base}{path}"
        try:
            resp = self._http.post(url, headers=self._headers(), json=json_body)
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                self._token_manager.invalidate()
            raise classify_error(_scrub_credentials(f"{e.response.status_code}: {e.response.text}")) from e
        except httpx.HTTPError as e:
            raise GoogleHomeError(_scrub_credentials(str(e))) from e

    # ------------------------------------------------------------------
    # Structures & rooms
    # ------------------------------------------------------------------

    def list_structures(self) -> list[StructureInfo]:
        """List all structures (homes)."""
        data = self._get("/structures")
        return [StructureInfo.from_api(s) for s in data.get("structures", [])]

    def get_structure(self, structure_id: str) -> StructureInfo:
        """Get a single structure by ID."""
        data = self._get(f"/structures/{structure_id}")
        return StructureInfo.from_api(data)

    def list_rooms(self, structure_id: str) -> list[RoomInfo]:
        """List rooms in a structure."""
        data = self._get(f"/structures/{structure_id}/rooms")
        return [RoomInfo.from_api(r) for r in data.get("rooms", [])]

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    def list_devices(self) -> list[DeviceInfo]:
        """List all devices across all structures."""
        data = self._get("/devices")
        return [DeviceInfo.from_api(d) for d in data.get("devices", [])]

    def get_device(self, device_id: str) -> DeviceInfo:
        """Get a single device by ID."""
        data = self._get(f"/devices/{device_id}")
        return DeviceInfo.from_api(data)

    def execute_command(self, device_id: str, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a command on a device.

        Args:
            device_id: Device resource ID
            command: Full command name (e.g. sdm.devices.traits.ThermostatMode.SetMode)
            params: Command parameters

        Returns:
            Command response (may contain stream URLs, image URLs, etc.)
        """
        body: dict[str, Any] = {"command": command, "params": params or {}}
        return self._post(f"/devices/{device_id}:executeCommand", body)

    # ------------------------------------------------------------------
    # Convenience: filtered device queries
    # ------------------------------------------------------------------

    def list_devices_by_type(self, device_type: str) -> list[DeviceInfo]:
        """List devices filtered by type (e.g. sdm.devices.types.THERMOSTAT)."""
        return [d for d in self.list_devices() if d.device_type == device_type]

    def find_device(self, name_or_id: str) -> DeviceInfo | None:
        """Find a device by custom name or device ID (case-insensitive name match)."""
        devices = self.list_devices()
        lower = name_or_id.lower()
        for device in devices:
            if device.device_id == name_or_id:
                return device
            if device.custom_name.lower() == lower:
                return device
        return None

    # ------------------------------------------------------------------
    # Info / health
    # ------------------------------------------------------------------

    def info(self) -> dict[str, Any]:
        """Health check: list structures, device counts, write gate status."""
        try:
            structures = self.list_structures()
            devices = self.list_devices()
        except AuthError:
            return {
                "status": "auth_error",
                "message": "Failed to authenticate — check credentials",
                "write_enabled": self._config.write_enabled,
            }
        except GoogleHomeError as e:
            return {
                "status": "error",
                "message": str(e),
                "write_enabled": self._config.write_enabled,
            }

        type_counts: dict[str, int] = {}
        for d in devices:
            label = d.type_label
            type_counts[label] = type_counts.get(label, 0) + 1

        return {
            "status": "ok",
            "project_id": self._config.project_id,
            "structures": len(structures),
            "devices": len(devices),
            "device_types": type_counts,
            "write_enabled": self._config.write_enabled,
            "pubsub_configured": self._config.pubsub_subscription is not None,
        }

    # ------------------------------------------------------------------
    # Pub/Sub events (optional)
    # ------------------------------------------------------------------

    def pull_events(self, max_messages: int = 10) -> list[dict[str, Any]]:
        """Pull events from Pub/Sub subscription.

        Requires GOOGLE_HOME_PUBSUB_SUBSCRIPTION to be set.
        Returns list of event dicts with timestamp, device, event type.
        """
        if not self._config.pubsub_subscription:
            raise GoogleHomeError("Pub/Sub subscription not configured. Set GOOGLE_HOME_PUBSUB_SUBSCRIPTION.")

        sub = self._config.pubsub_subscription
        url = f"https://pubsub.googleapis.com/v1/{sub}:pull"
        try:
            resp = self._http.post(
                url,
                headers=self._headers(),
                json={"maxMessages": max_messages},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            messages = data.get("receivedMessages", [])

            # Acknowledge messages
            ack_ids = [m["ackId"] for m in messages if "ackId" in m]
            if ack_ids:
                self._http.post(
                    f"https://pubsub.googleapis.com/v1/{sub}:acknowledge",
                    headers=self._headers(),
                    json={"ackIds": ack_ids},
                    timeout=10.0,
                )

            return [self._parse_event(m) for m in messages]

        except httpx.HTTPStatusError as e:
            raise classify_error(_scrub_credentials(f"{e.response.status_code}: {e.response.text}")) from e
        except httpx.HTTPError as e:
            raise GoogleHomeError(_scrub_credentials(str(e))) from e

    def _parse_event(self, message: dict[str, Any]) -> dict[str, Any]:
        """Parse a Pub/Sub message into a structured event dict."""
        import base64
        import json

        pub_msg = message.get("message", {})
        data_b64 = pub_msg.get("data", "")
        try:
            payload = json.loads(base64.b64decode(data_b64))
        except Exception:
            payload = {"raw": data_b64}

        return {
            "timestamp": pub_msg.get("publishTime"),
            "event_id": pub_msg.get("messageId"),
            "payload": payload,
        }
