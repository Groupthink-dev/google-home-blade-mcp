"""Token-efficient output formatters for Google Home Blade MCP.

Design principles:
- One line per entity (pipe-delimited)
- Null-field omission (never include empty/None values)
- Grouped output for multi-structure views
- Minimal tokens per device (~20-30 tokens)
"""

from __future__ import annotations

from typing import Any

from google_home_blade_mcp.models import (
    DEVICE_TYPE_CAMERA,
    DEVICE_TYPE_DOORBELL,
    DEVICE_TYPE_THERMOSTAT,
    DeviceInfo,
    RoomInfo,
    StructureInfo,
)
from google_home_blade_mcp.traits import get_camera_summary, get_thermostat_summary

# ---------------------------------------------------------------------------
# Info / health
# ---------------------------------------------------------------------------


def format_info(info: dict[str, Any]) -> str:
    """Format health check output."""
    parts = [f"status={info['status']}"]

    if info["status"] != "ok":
        parts.append(f"message={info.get('message', 'unknown')}")
    else:
        parts.append(f"project={info.get('project_id', '?')}")
        parts.append(f"structures={info.get('structures', 0)}")
        parts.append(f"devices={info.get('devices', 0)}")

        type_counts = info.get("device_types", {})
        if type_counts:
            types_str = ", ".join(f"{k}={v}" for k, v in sorted(type_counts.items()))
            parts.append(types_str)

    parts.append(f"write={'on' if info.get('write_enabled') else 'off'}")
    if info.get("pubsub_configured"):
        parts.append("pubsub=configured")

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Structures & rooms
# ---------------------------------------------------------------------------


def format_structure_list(structures: list[StructureInfo]) -> str:
    """Format list of structures."""
    if not structures:
        return "(no structures)"
    lines = []
    for s in structures:
        parts = [s.display_name or "(unnamed)"]
        parts.append(f"id={s.structure_id}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def format_room_list(rooms: list[RoomInfo], structure_name: str | None = None) -> str:
    """Format list of rooms."""
    if not rooms:
        return "(no rooms)"
    header = f"## {structure_name} ({len(rooms)} rooms)\n" if structure_name else ""
    lines = []
    for r in rooms:
        parts = [r.display_name or "(unnamed)"]
        parts.append(f"id={r.room_id}")
        lines.append(" | ".join(parts))
    return header + "\n".join(lines)


# ---------------------------------------------------------------------------
# Device list (compact)
# ---------------------------------------------------------------------------


def format_device_line(device: DeviceInfo) -> str:
    """Format a single device as a compact one-liner."""
    parts = [device.custom_name, device.type_label]

    if device.room_name:
        parts.append(f"room={device.room_name}")

    status = "online" if device.is_online else "offline"
    parts.append(status)

    # Add key trait data inline
    if device.device_type == DEVICE_TYPE_THERMOSTAT:
        summary = get_thermostat_summary(device)
        if "ambient_c" in summary:
            parts.append(f"{summary['ambient_c']}°C")
        if "mode" in summary:
            parts.append(f"mode={summary['mode']}")
        if "hvac_status" in summary:
            parts.append(f"hvac={summary['hvac_status']}")

    elif device.device_type in (DEVICE_TYPE_CAMERA, DEVICE_TYPE_DOORBELL):
        summary = get_camera_summary(device)
        caps = []
        if summary.get("has_motion"):
            caps.append("motion")
        if summary.get("has_person"):
            caps.append("person")
        if summary.get("has_sound"):
            caps.append("sound")
        if summary.get("has_chime"):
            caps.append("chime")
        if caps:
            parts.append(f"events={','.join(caps)}")

    parts.append(f"id={device.device_id}")
    return " | ".join(parts)


def format_device_list(devices: list[DeviceInfo]) -> str:
    """Format list of devices, one per line."""
    if not devices:
        return "(no devices)"
    return "\n".join(format_device_line(d) for d in devices)


# ---------------------------------------------------------------------------
# Device detail (full)
# ---------------------------------------------------------------------------


def format_device_detail(device: DeviceInfo) -> str:
    """Format full device detail with all traits."""
    lines = [
        f"# {device.custom_name}",
        f"type={device.type_label} | {'online' if device.is_online else 'offline'} | id={device.device_id}",
    ]

    if device.room_name:
        lines.append(f"room={device.room_name}")

    # Thermostat traits
    if device.device_type == DEVICE_TYPE_THERMOSTAT:
        summary = get_thermostat_summary(device)
        if summary:
            lines.append("")
            lines.append("## Thermostat")
            for key, value in summary.items():
                lines.append(f"  {key}={value}")

    # Camera traits
    if device.device_type in (DEVICE_TYPE_CAMERA, DEVICE_TYPE_DOORBELL):
        summary = get_camera_summary(device)
        if summary:
            lines.append("")
            lines.append("## Camera")
            for key, value in summary.items():
                lines.append(f"  {key}={value}")

    # Raw traits (for devices without specific formatting)
    other_traits = {
        k.split(".")[-1]: v
        for k, v in device.traits.items()
        if not any(
            k.endswith(t)
            for t in (
                "Info",
                "Connectivity",
                "Temperature",
                "Humidity",
                "ThermostatMode",
                "ThermostatTemperatureSetpoint",
                "ThermostatEco",
                "ThermostatHvac",
                "Fan",
                "Settings",
                "CameraLiveStream",
                "CameraMotion",
                "CameraPerson",
                "CameraSound",
                "CameraEventImage",
                "DoorbellChime",
            )
        )
    }
    if other_traits:
        lines.append("")
        lines.append("## Other Traits")
        for trait_name, trait_data in other_traits.items():
            if isinstance(trait_data, dict) and trait_data:
                for tk, tv in trait_data.items():
                    lines.append(f"  {trait_name}.{tk}={tv}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Thermostat summary (batch view)
# ---------------------------------------------------------------------------


def format_thermostat_line(device: DeviceInfo) -> str:
    """Format thermostat as a compact status line."""
    summary = get_thermostat_summary(device)
    parts = [device.custom_name]

    if device.room_name:
        parts.append(device.room_name)

    if "ambient_c" in summary:
        parts.append(f"ambient={summary['ambient_c']}°C")
    if "humidity_pct" in summary:
        parts.append(f"humidity={summary['humidity_pct']}%")
    if "mode" in summary:
        parts.append(f"mode={summary['mode']}")
    if "heat_setpoint_c" in summary:
        parts.append(f"heat→{summary['heat_setpoint_c']}°C")
    if "cool_setpoint_c" in summary:
        parts.append(f"cool→{summary['cool_setpoint_c']}°C")
    if "eco_mode" in summary and summary["eco_mode"] != "OFF":
        parts.append(f"eco={summary['eco_mode']}")
    if "hvac_status" in summary:
        parts.append(f"hvac={summary['hvac_status']}")

    status = "online" if device.is_online else "OFFLINE"
    parts.append(status)
    parts.append(f"id={device.device_id}")

    return " | ".join(parts)


def format_thermostat_list(devices: list[DeviceInfo]) -> str:
    """Format all thermostats as compact status lines."""
    if not devices:
        return "(no thermostats)"
    return "\n".join(format_thermostat_line(d) for d in devices)


# ---------------------------------------------------------------------------
# Status dashboard (compact)
# ---------------------------------------------------------------------------


def format_status_dashboard(devices: list[DeviceInfo]) -> str:
    """Format a compact status dashboard for all devices."""
    if not devices:
        return "(no devices)"

    online = sum(1 for d in devices if d.is_online)
    header = f"## Devices: {len(devices)} total, {online} online\n"

    lines = [format_device_line(d) for d in devices]
    return header + "\n".join(lines)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def format_events(events: list[dict[str, Any]]) -> str:
    """Format Pub/Sub events."""
    if not events:
        return "(no events)"
    lines = []
    for evt in events:
        parts = []
        if evt.get("timestamp"):
            parts.append(str(evt["timestamp"]))
        payload = evt.get("payload", {})
        if isinstance(payload, dict):
            if "resourceUpdate" in payload:
                update = payload["resourceUpdate"]
                if "traits" in update:
                    parts.append("trait_update")
                    for trait, data in update["traits"].items():
                        short_trait = trait.split(".")[-1]
                        parts.append(f"{short_trait}={data}")
                if "events" in update:
                    for event_type, event_data in update["events"].items():
                        short_type = event_type.split(".")[-1]
                        parts.append(f"event={short_type}")
                        if isinstance(event_data, dict) and "eventId" in event_data:
                            parts.append(f"event_id={event_data['eventId']}")
        if evt.get("event_id"):
            parts.append(f"msg_id={evt['event_id']}")
        lines.append(" | ".join(parts) if parts else str(evt))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command response
# ---------------------------------------------------------------------------


def format_command_response(response: dict[str, Any]) -> str:
    """Format a device command response."""
    results = response.get("results", {})
    if not results:
        return "Command executed successfully."

    parts = []
    # Camera stream responses
    if "streamUrls" in results:
        urls = results["streamUrls"]
        if "rtspUrl" in urls:
            parts.append(f"rtsp_url={urls['rtspUrl']}")
    if "answerSdp" in results:
        parts.append("webrtc_answer=<sdp>")
    if "streamToken" in results:
        parts.append(f"stream_token={results['streamToken']}")
    if "streamExtensionToken" in results:
        parts.append(f"extension_token={results['streamExtensionToken']}")
    if "expiresAt" in results:
        parts.append(f"expires={results['expiresAt']}")

    # Camera image responses
    if "url" in results:
        parts.append(f"image_url={results['url']}")
    if "token" in results:
        parts.append(f"image_token={results['token']}")

    if parts:
        return " | ".join(parts)
    # Fallback: dump response as key=value
    return " | ".join(f"{k}={v}" for k, v in results.items())
