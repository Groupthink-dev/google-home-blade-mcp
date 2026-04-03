"""SDM device trait parsing and command building.

Extracts structured data from the trait-based device model,
and builds command payloads for device control.
"""

from __future__ import annotations

from google_home_blade_mcp.models import TRAIT_PREFIX, DeviceInfo

# ---------------------------------------------------------------------------
# Trait extraction helpers
# ---------------------------------------------------------------------------


def get_trait(device: DeviceInfo, trait_name: str) -> dict[str, object]:
    """Get a trait dict by short name (e.g. 'Temperature') or full name."""
    if not trait_name.startswith(TRAIT_PREFIX):
        trait_name = f"{TRAIT_PREFIX}{trait_name}"
    return dict(device.traits.get(trait_name, {}))


def has_trait(device: DeviceInfo, trait_name: str) -> bool:
    """Check if device has a trait."""
    if not trait_name.startswith(TRAIT_PREFIX):
        trait_name = f"{TRAIT_PREFIX}{trait_name}"
    return trait_name in device.traits


# ---------------------------------------------------------------------------
# Thermostat trait extraction
# ---------------------------------------------------------------------------


def get_thermostat_summary(device: DeviceInfo) -> dict[str, object]:
    """Extract thermostat state as a flat dict."""
    result: dict[str, object] = {}

    temp = get_trait(device, "Temperature")
    if temp:
        result["ambient_c"] = temp.get("ambientTemperatureCelsius")

    humidity = get_trait(device, "Humidity")
    if humidity:
        result["humidity_pct"] = humidity.get("ambientHumidityPercent")

    mode = get_trait(device, "ThermostatMode")
    if mode:
        result["mode"] = mode.get("mode")
        result["available_modes"] = mode.get("availableModes")

    setpoint = get_trait(device, "ThermostatTemperatureSetpoint")
    if setpoint:
        result["heat_setpoint_c"] = setpoint.get("heatCelsius")
        result["cool_setpoint_c"] = setpoint.get("coolCelsius")

    eco = get_trait(device, "ThermostatEco")
    if eco:
        result["eco_mode"] = eco.get("mode")
        result["eco_heat_c"] = eco.get("heatCelsius")
        result["eco_cool_c"] = eco.get("coolCelsius")

    hvac = get_trait(device, "ThermostatHvac")
    if hvac:
        result["hvac_status"] = hvac.get("status")

    fan = get_trait(device, "Fan")
    if fan:
        result["fan_mode"] = fan.get("timerMode")
        result["fan_timeout"] = fan.get("timerTimeout")

    settings = get_trait(device, "Settings")
    if settings:
        result["temp_scale"] = settings.get("temperatureScale")

    return {k: v for k, v in result.items() if v is not None}


# ---------------------------------------------------------------------------
# Camera trait extraction
# ---------------------------------------------------------------------------


def get_camera_summary(device: DeviceInfo) -> dict[str, object]:
    """Extract camera capabilities and event support."""
    result: dict[str, object] = {}

    stream = get_trait(device, "CameraLiveStream")
    if stream:
        protocols = stream.get("supportedProtocols", [])
        result["stream_protocols"] = protocols
        result["max_resolution"] = stream.get("maxVideoResolution")

    result["has_motion"] = has_trait(device, "CameraMotion")
    result["has_person"] = has_trait(device, "CameraPerson")
    result["has_sound"] = has_trait(device, "CameraSound")

    if has_trait(device, "DoorbellChime"):
        result["has_chime"] = True

    return {k: v for k, v in result.items() if v is not None}


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------


def build_thermostat_mode_command(mode: str) -> dict[str, object]:
    """Build ThermostatMode.SetMode command payload."""
    return {
        "command": f"{TRAIT_PREFIX}ThermostatMode.SetMode",
        "params": {"mode": mode.upper()},
    }


def build_thermostat_setpoint_command(
    heat_celsius: float | None = None,
    cool_celsius: float | None = None,
) -> dict[str, object]:
    """Build ThermostatTemperatureSetpoint command payload.

    Automatically selects SetHeat, SetCool, or SetRange based on provided values.
    """
    if heat_celsius is not None and cool_celsius is not None:
        return {
            "command": f"{TRAIT_PREFIX}ThermostatTemperatureSetpoint.SetRange",
            "params": {
                "heatCelsius": heat_celsius,
                "coolCelsius": cool_celsius,
            },
        }
    elif heat_celsius is not None:
        return {
            "command": f"{TRAIT_PREFIX}ThermostatTemperatureSetpoint.SetHeat",
            "params": {"heatCelsius": heat_celsius},
        }
    elif cool_celsius is not None:
        return {
            "command": f"{TRAIT_PREFIX}ThermostatTemperatureSetpoint.SetCool",
            "params": {"coolCelsius": cool_celsius},
        }
    else:
        raise ValueError("At least one of heat_celsius or cool_celsius must be provided")


def build_thermostat_eco_command(eco_mode: str) -> dict[str, object]:
    """Build ThermostatEco.SetEcoMode command payload."""
    return {
        "command": f"{TRAIT_PREFIX}ThermostatEco.SetEcoMode",
        "params": {"mode": eco_mode.upper()},
    }


def build_fan_command(timer_mode: str, duration_seconds: int | None = None) -> dict[str, object]:
    """Build Fan.SetTimer command payload."""
    params: dict[str, object] = {"timerMode": timer_mode.upper()}
    if duration_seconds is not None:
        params["duration"] = f"{duration_seconds}s"
    return {
        "command": f"{TRAIT_PREFIX}Fan.SetTimer",
        "params": params,
    }


def build_camera_stream_command(protocol: str = "WEB_RTC") -> dict[str, object]:
    """Build CameraLiveStream.Generate*Stream command payload."""
    if protocol.upper() == "WEB_RTC":
        return {
            "command": f"{TRAIT_PREFIX}CameraLiveStream.GenerateWebRtcStream",
            "params": {"offerSdp": ""},
        }
    else:
        return {
            "command": f"{TRAIT_PREFIX}CameraLiveStream.GenerateRtspStream",
            "params": {},
        }


def build_camera_image_command(event_id: str) -> dict[str, object]:
    """Build CameraEventImage.GenerateImage command payload."""
    return {
        "command": f"{TRAIT_PREFIX}CameraEventImage.GenerateImage",
        "params": {"eventId": event_id},
    }


def build_generic_command(command: str, params: dict[str, object] | None = None) -> dict[str, object]:
    """Build a generic device command payload."""
    result: dict[str, object] = {"command": command}
    if params:
        result["params"] = params
    else:
        result["params"] = {}
    return result
