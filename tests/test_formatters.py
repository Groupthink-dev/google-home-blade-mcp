"""Tests for token-efficient output formatters."""

from __future__ import annotations

from google_home_blade_mcp.formatters import (
    format_command_response,
    format_device_detail,
    format_device_line,
    format_device_list,
    format_events,
    format_info,
    format_room_list,
    format_status_dashboard,
    format_structure_list,
    format_thermostat_line,
    format_thermostat_list,
)
from tests.conftest import make_camera, make_doorbell, make_room, make_structure, make_thermostat


class TestFormatInfo:
    def test_ok_status(self) -> None:
        info = {
            "status": "ok",
            "project_id": "proj-1",
            "structures": 2,
            "devices": 5,
            "device_types": {"Thermostat": 3, "Camera": 2},
            "write_enabled": True,
            "pubsub_configured": True,
        }
        result = format_info(info)
        assert "status=ok" in result
        assert "devices=5" in result
        assert "write=on" in result
        assert "pubsub=configured" in result

    def test_error_status(self) -> None:
        info = {"status": "auth_error", "message": "bad creds", "write_enabled": False}
        result = format_info(info)
        assert "auth_error" in result
        assert "bad creds" in result
        assert "write=off" in result


class TestFormatStructures:
    def test_list(self) -> None:
        structures = [make_structure("s1", "Home"), make_structure("s2", "Office")]
        result = format_structure_list(structures)
        assert "Home" in result
        assert "Office" in result
        assert "id=s1" in result

    def test_empty(self) -> None:
        assert format_structure_list([]) == "(no structures)"


class TestFormatRooms:
    def test_list(self) -> None:
        rooms = [make_room("r1", "Kitchen"), make_room("r2", "Bedroom")]
        result = format_room_list(rooms)
        assert "Kitchen" in result
        assert "Bedroom" in result

    def test_with_header(self) -> None:
        rooms = [make_room()]
        result = format_room_list(rooms, "My Home")
        assert "## My Home" in result

    def test_empty(self) -> None:
        assert format_room_list([]) == "(no rooms)"


class TestFormatDeviceLine:
    def test_thermostat_line(self) -> None:
        device = make_thermostat()
        line = format_device_line(device)
        assert "Living Room" in line
        assert "Thermostat" in line
        assert "21.5°C" in line
        assert "mode=HEAT" in line
        assert "online" in line

    def test_camera_line(self) -> None:
        device = make_camera(has_motion=True, has_person=True)
        line = format_device_line(device)
        assert "Camera" in line
        assert "events=motion,person" in line

    def test_doorbell_line(self) -> None:
        device = make_doorbell()
        line = format_device_line(device)
        assert "Doorbell" in line
        assert "chime" in line

    def test_offline_device(self) -> None:
        device = make_thermostat(online=False)
        line = format_device_line(device)
        assert "offline" in line


class TestFormatDeviceList:
    def test_multiple_devices(self) -> None:
        devices = [make_thermostat(), make_camera()]
        result = format_device_list(devices)
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_empty(self) -> None:
        assert format_device_list([]) == "(no devices)"


class TestFormatDeviceDetail:
    def test_thermostat_detail(self) -> None:
        device = make_thermostat()
        detail = format_device_detail(device)
        assert "# Living Room" in detail
        assert "Thermostat" in detail
        assert "## Thermostat" in detail
        assert "ambient_c=21.5" in detail
        assert "mode=HEAT" in detail

    def test_camera_detail(self) -> None:
        device = make_camera()
        detail = format_device_detail(device)
        assert "# Front Door Camera" in detail
        assert "## Camera" in detail
        assert "has_motion=True" in detail


class TestFormatThermostatLine:
    def test_full_thermostat(self) -> None:
        device = make_thermostat()
        line = format_thermostat_line(device)
        assert "Living Room" in line
        assert "ambient=21.5°C" in line
        assert "humidity=45%" in line
        assert "mode=HEAT" in line
        assert "heat→22.0°C" in line
        assert "hvac=HEATING" in line

    def test_empty_list(self) -> None:
        assert format_thermostat_list([]) == "(no thermostats)"


class TestFormatStatusDashboard:
    def test_dashboard(self) -> None:
        devices = [make_thermostat(), make_camera(), make_doorbell()]
        result = format_status_dashboard(devices)
        assert "3 total" in result
        assert "3 online" in result

    def test_empty(self) -> None:
        assert format_status_dashboard([]) == "(no devices)"


class TestFormatEvents:
    def test_empty(self) -> None:
        assert format_events([]) == "(no events)"

    def test_trait_update_event(self) -> None:
        events = [
            {
                "timestamp": "2026-04-03T10:00:00Z",
                "event_id": "msg-1",
                "payload": {
                    "resourceUpdate": {
                        "traits": {"sdm.devices.traits.Temperature": {"ambientTemperatureCelsius": 22.0}}
                    }
                },
            }
        ]
        result = format_events(events)
        assert "trait_update" in result
        assert "Temperature" in result

    def test_device_event(self) -> None:
        events = [
            {
                "timestamp": "2026-04-03T10:00:00Z",
                "event_id": "msg-2",
                "payload": {
                    "resourceUpdate": {"events": {"sdm.devices.events.CameraMotion.Motion": {"eventId": "evt-abc"}}}
                },
            }
        ]
        result = format_events(events)
        assert "event=Motion" in result
        assert "event_id=evt-abc" in result


class TestFormatCommandResponse:
    def test_empty_results(self) -> None:
        assert format_command_response({"results": {}}) == "Command executed successfully."

    def test_rtsp_stream(self) -> None:
        resp = {"results": {"streamUrls": {"rtspUrl": "rtsp://example.com/stream"}, "streamToken": "tok-1"}}
        result = format_command_response(resp)
        assert "rtsp_url=" in result
        assert "stream_token=tok-1" in result

    def test_image_response(self) -> None:
        resp = {"results": {"url": "https://example.com/image.jpg", "token": "img-tok"}}
        result = format_command_response(resp)
        assert "image_url=" in result
        assert "image_token=img-tok" in result
