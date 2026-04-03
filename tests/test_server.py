"""Tests for MCP server tools."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from google_home_blade_mcp.models import GoogleHomeError
from google_home_blade_mcp.server import (
    ghome_camera_image,
    ghome_camera_stream,
    ghome_command,
    ghome_device,
    ghome_devices,
    ghome_events,
    ghome_fan_set,
    ghome_info,
    ghome_rooms,
    ghome_status,
    ghome_structures,
    ghome_thermostat_eco,
    ghome_thermostat_mode,
    ghome_thermostat_setpoint,
    ghome_thermostats,
)
from tests.conftest import make_camera, make_thermostat


@pytest.fixture(autouse=True)
def _patch_client(mock_client: MagicMock) -> None:  # type: ignore[type-arg]
    """Patch the client singleton for all server tests."""
    with patch("google_home_blade_mcp.server._get_client", return_value=mock_client):
        yield


# ===========================================================================
# Read tools
# ===========================================================================


class TestGhomeInfo:
    async def test_info(self, mock_client: MagicMock) -> None:
        result = await ghome_info()
        assert "status=ok" in result
        assert "devices=3" in result

    async def test_info_error(self, mock_client: MagicMock) -> None:
        mock_client.info.side_effect = GoogleHomeError("connection failed")
        result = await ghome_info()
        assert "Error:" in result


class TestGhomeStructures:
    async def test_list(self, mock_client: MagicMock) -> None:
        result = await ghome_structures()
        assert "My Home" in result


class TestGhomeRooms:
    async def test_list(self, mock_client: MagicMock) -> None:
        result = await ghome_rooms(structure_id="struct-1")
        assert "Living Room" in result
        assert "Entry" in result


class TestGhomeDevices:
    async def test_list_all(self, mock_client: MagicMock) -> None:
        result = await ghome_devices()
        assert "Thermostat" in result
        assert "Camera" in result

    async def test_filter_by_type(self, mock_client: MagicMock) -> None:
        result = await ghome_devices(device_type="THERMOSTAT")
        mock_client.list_devices_by_type.assert_called_once()
        assert "Thermostat" in result


class TestGhomeDevice:
    async def test_found(self, mock_client: MagicMock) -> None:
        result = await ghome_device(device="Living Room")
        assert "# Living Room" in result

    async def test_not_found(self, mock_client: MagicMock) -> None:
        mock_client.find_device.return_value = None
        result = await ghome_device(device="Nonexistent")
        assert "not found" in result.lower()


class TestGhomeStatus:
    async def test_dashboard(self, mock_client: MagicMock) -> None:
        result = await ghome_status()
        assert "3 total" in result


class TestGhomeThermostats:
    async def test_list(self, mock_client: MagicMock) -> None:
        result = await ghome_thermostats()
        assert "Living Room" in result


class TestGhomeEvents:
    async def test_no_events(self, mock_client: MagicMock) -> None:
        result = await ghome_events()
        assert "(no events)" in result

    async def test_pubsub_not_configured(self, mock_client: MagicMock) -> None:
        mock_client.pull_events.side_effect = GoogleHomeError("Pub/Sub subscription not configured")
        result = await ghome_events()
        assert "Pub/Sub" in result


# ===========================================================================
# Write-gated tools
# ===========================================================================


class TestWriteGate:
    """All write tools should return error when writes disabled."""

    async def test_thermostat_mode_blocked(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_HOME_WRITE_ENABLED": "false"}):
            result = await ghome_thermostat_mode(device="Living Room", mode="HEAT")
            assert "disabled" in result.lower()

    async def test_thermostat_setpoint_blocked(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_HOME_WRITE_ENABLED": "false"}):
            result = await ghome_thermostat_setpoint(device="Living Room", heat_celsius=22.0)
            assert "disabled" in result.lower()

    async def test_thermostat_eco_blocked(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_HOME_WRITE_ENABLED": "false"}):
            result = await ghome_thermostat_eco(device="Living Room", eco_mode="MANUAL_ECO")
            assert "disabled" in result.lower()

    async def test_fan_set_blocked(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_HOME_WRITE_ENABLED": "false"}):
            result = await ghome_fan_set(device="Living Room", timer_mode="ON")
            assert "disabled" in result.lower()

    async def test_camera_stream_blocked(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_HOME_WRITE_ENABLED": "false"}):
            result = await ghome_camera_stream(device="Front Door Camera")
            assert "disabled" in result.lower()

    async def test_camera_image_blocked(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_HOME_WRITE_ENABLED": "false"}):
            result = await ghome_camera_image(device="Front Door Camera", event_id="evt-1")
            assert "disabled" in result.lower()

    async def test_command_blocked(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_HOME_WRITE_ENABLED": "false"}):
            result = await ghome_command(device="Living Room", command="some.cmd", confirm=True)
            assert "disabled" in result.lower()


class TestWriteOperations:
    """Write tools with GOOGLE_HOME_WRITE_ENABLED=true."""

    @pytest.fixture(autouse=True)
    def _enable_write(self) -> None:  # type: ignore[type-arg]
        with patch.dict(os.environ, {"GOOGLE_HOME_WRITE_ENABLED": "true"}):
            yield

    async def test_thermostat_mode(self, mock_client: MagicMock) -> None:
        result = await ghome_thermostat_mode(device="Living Room", mode="COOL")
        assert "COOL" in result
        mock_client.execute_command.assert_called_once()

    async def test_thermostat_setpoint_heat(self, mock_client: MagicMock) -> None:
        result = await ghome_thermostat_setpoint(device="Living Room", heat_celsius=22.0)
        assert "heat→22.0°C" in result

    async def test_thermostat_setpoint_no_values(self, mock_client: MagicMock) -> None:
        result = await ghome_thermostat_setpoint(device="Living Room")
        assert "Error:" in result

    async def test_thermostat_eco(self, mock_client: MagicMock) -> None:
        result = await ghome_thermostat_eco(device="Living Room", eco_mode="MANUAL_ECO")
        assert "MANUAL_ECO" in result

    async def test_fan_set(self, mock_client: MagicMock) -> None:
        result = await ghome_fan_set(device="Living Room", timer_mode="ON", duration_seconds=900)
        assert "ON" in result

    async def test_camera_stream(self, mock_client: MagicMock) -> None:
        mock_client.find_device.return_value = make_camera()
        result = await ghome_camera_stream(device="Front Door Camera")
        assert "Stream for Front Door Camera" in result

    async def test_camera_stream_not_camera(self, mock_client: MagicMock) -> None:
        mock_client.find_device.return_value = make_thermostat()
        result = await ghome_camera_stream(device="Living Room")
        assert "not a camera" in result.lower()

    async def test_camera_image(self, mock_client: MagicMock) -> None:
        mock_client.find_device.return_value = make_camera()
        result = await ghome_camera_image(device="Front Door Camera", event_id="evt-1")
        assert "Image for Front Door Camera" in result

    async def test_device_not_found(self, mock_client: MagicMock) -> None:
        mock_client.find_device.return_value = None
        result = await ghome_thermostat_mode(device="Ghost", mode="HEAT")
        assert "not found" in result.lower()


class TestConfirmGate:
    @pytest.fixture(autouse=True)
    def _enable_write(self) -> None:  # type: ignore[type-arg]
        with patch.dict(os.environ, {"GOOGLE_HOME_WRITE_ENABLED": "true"}):
            yield

    async def test_command_without_confirm(self, mock_client: MagicMock) -> None:
        result = await ghome_command(device="Living Room", command="some.cmd")
        assert "confirm=true" in result.lower()
        mock_client.execute_command.assert_not_called()

    async def test_command_with_confirm(self, mock_client: MagicMock) -> None:
        result = await ghome_command(device="Living Room", command="some.cmd", params={"key": "val"}, confirm=True)
        assert "Command on Living Room" in result
        mock_client.execute_command.assert_called_once()
