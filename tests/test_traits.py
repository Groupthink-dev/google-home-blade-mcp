"""Tests for trait parsing and command building."""

from __future__ import annotations

import pytest

from google_home_blade_mcp.traits import (
    build_camera_image_command,
    build_camera_stream_command,
    build_fan_command,
    build_generic_command,
    build_thermostat_eco_command,
    build_thermostat_mode_command,
    build_thermostat_setpoint_command,
    get_camera_summary,
    get_thermostat_summary,
    get_trait,
    has_trait,
)
from tests.conftest import make_camera, make_doorbell, make_thermostat


class TestTraitExtraction:
    def test_get_trait_short_name(self) -> None:
        device = make_thermostat()
        trait = get_trait(device, "Temperature")
        assert trait.get("ambientTemperatureCelsius") == 21.5

    def test_get_trait_full_name(self) -> None:
        device = make_thermostat()
        trait = get_trait(device, "sdm.devices.traits.Temperature")
        assert trait.get("ambientTemperatureCelsius") == 21.5

    def test_get_trait_missing(self) -> None:
        device = make_thermostat()
        assert get_trait(device, "DoorbellChime") == {}

    def test_has_trait(self) -> None:
        device = make_thermostat()
        assert has_trait(device, "Temperature") is True
        assert has_trait(device, "DoorbellChime") is False


class TestThermostatSummary:
    def test_full_summary(self) -> None:
        device = make_thermostat()
        summary = get_thermostat_summary(device)
        assert summary["ambient_c"] == 21.5
        assert summary["humidity_pct"] == 45
        assert summary["mode"] == "HEAT"
        assert summary["heat_setpoint_c"] == 22.0
        assert summary["hvac_status"] == "HEATING"
        assert summary["eco_mode"] == "OFF"
        assert summary["temp_scale"] == "CELSIUS"

    def test_null_omission(self) -> None:
        device = make_thermostat()
        summary = get_thermostat_summary(device)
        # cool_setpoint_c should be omitted (not set for HEAT mode)
        assert "cool_setpoint_c" not in summary


class TestCameraSummary:
    def test_camera_with_events(self) -> None:
        device = make_camera(has_motion=True, has_person=True, has_sound=True)
        summary = get_camera_summary(device)
        assert summary["has_motion"] is True
        assert summary["has_person"] is True
        assert summary["has_sound"] is True
        assert summary["stream_protocols"] == ["WEB_RTC"]

    def test_doorbell_has_chime(self) -> None:
        device = make_doorbell()
        summary = get_camera_summary(device)
        assert summary["has_chime"] is True
        assert summary["has_motion"] is True
        assert summary["has_person"] is True


class TestCommandBuilders:
    def test_thermostat_mode(self) -> None:
        cmd = build_thermostat_mode_command("heat")
        assert cmd["command"] == "sdm.devices.traits.ThermostatMode.SetMode"
        assert cmd["params"]["mode"] == "HEAT"

    def test_thermostat_setpoint_heat(self) -> None:
        cmd = build_thermostat_setpoint_command(heat_celsius=22.0)
        assert "SetHeat" in str(cmd["command"])
        assert cmd["params"]["heatCelsius"] == 22.0

    def test_thermostat_setpoint_cool(self) -> None:
        cmd = build_thermostat_setpoint_command(cool_celsius=25.0)
        assert "SetCool" in str(cmd["command"])
        assert cmd["params"]["coolCelsius"] == 25.0

    def test_thermostat_setpoint_range(self) -> None:
        cmd = build_thermostat_setpoint_command(heat_celsius=20.0, cool_celsius=25.0)
        assert "SetRange" in str(cmd["command"])
        assert cmd["params"]["heatCelsius"] == 20.0
        assert cmd["params"]["coolCelsius"] == 25.0

    def test_thermostat_setpoint_no_values(self) -> None:
        with pytest.raises(ValueError, match="At least one"):
            build_thermostat_setpoint_command()

    def test_thermostat_eco(self) -> None:
        cmd = build_thermostat_eco_command("manual_eco")
        assert cmd["params"]["mode"] == "MANUAL_ECO"

    def test_fan_on(self) -> None:
        cmd = build_fan_command("on", 900)
        assert cmd["params"]["timerMode"] == "ON"
        assert cmd["params"]["duration"] == "900s"

    def test_fan_off(self) -> None:
        cmd = build_fan_command("off")
        assert cmd["params"]["timerMode"] == "OFF"
        assert "duration" not in cmd["params"]

    def test_camera_stream_webrtc(self) -> None:
        cmd = build_camera_stream_command("WEB_RTC")
        assert "GenerateWebRtcStream" in str(cmd["command"])

    def test_camera_stream_rtsp(self) -> None:
        cmd = build_camera_stream_command("RTSP")
        assert "GenerateRtspStream" in str(cmd["command"])

    def test_camera_image(self) -> None:
        cmd = build_camera_image_command("evt-123")
        assert "GenerateImage" in str(cmd["command"])
        assert cmd["params"]["eventId"] == "evt-123"

    def test_generic_command(self) -> None:
        cmd = build_generic_command("sdm.devices.traits.Fan.SetTimer", {"timerMode": "ON"})
        assert cmd["command"] == "sdm.devices.traits.Fan.SetTimer"
        assert cmd["params"]["timerMode"] == "ON"

    def test_generic_command_no_params(self) -> None:
        cmd = build_generic_command("some.command")
        assert cmd["params"] == {}
