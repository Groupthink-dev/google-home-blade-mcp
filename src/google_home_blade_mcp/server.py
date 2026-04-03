"""Google Home Blade MCP Server — device control, cameras, thermostats via SDM API.

Wraps the Google Smart Device Management API as MCP tools. Token-efficient
by default: compact output, null-field omission, batch operations.
Security-first: write gates, confirm gates, credential scrubbing.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from google_home_blade_mcp.client import GoogleHomeClient, GoogleHomeError
from google_home_blade_mcp.formatters import (
    format_command_response,
    format_device_detail,
    format_device_list,
    format_events,
    format_info,
    format_room_list,
    format_status_dashboard,
    format_structure_list,
    format_thermostat_list,
)
from google_home_blade_mcp.models import (
    DEVICE_TYPE_CAMERA,
    DEVICE_TYPE_DOORBELL,
    DEVICE_TYPE_THERMOSTAT,
    require_write,
)
from google_home_blade_mcp.traits import (
    build_camera_image_command,
    build_camera_stream_command,
    build_fan_command,
    build_generic_command,
    build_thermostat_eco_command,
    build_thermostat_mode_command,
    build_thermostat_setpoint_command,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transport configuration
# ---------------------------------------------------------------------------

TRANSPORT = os.environ.get("GOOGLE_HOME_MCP_TRANSPORT", "stdio")
HTTP_HOST = os.environ.get("GOOGLE_HOME_MCP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("GOOGLE_HOME_MCP_PORT", "8767"))

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "GoogleHomeBlade",
    instructions=(
        "Google Home / Nest device operations via SDM API. "
        "Query device state, control thermostats, stream cameras. "
        "Use ghome_status for compact dashboard. "
        "Write operations require GOOGLE_HOME_WRITE_ENABLED=true."
    ),
)

# Lazy-initialized client
_client: GoogleHomeClient | None = None


def _get_client() -> GoogleHomeClient:
    """Get or create the GoogleHomeClient singleton."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = GoogleHomeClient()
    return _client


def _error(e: GoogleHomeError) -> str:
    """Format a client error as a user-friendly string."""
    return f"Error: {e}"


async def _run(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a blocking client method in a thread."""
    return await asyncio.to_thread(fn, *args, **kwargs)


# ===========================================================================
# META (1 tool)
# ===========================================================================


@mcp.tool()
async def ghome_info() -> str:
    """Health check: API status, structures, device counts, write gate, Pub/Sub status."""
    try:
        info = await _run(_get_client().info)
        return format_info(info)
    except GoogleHomeError as e:
        return _error(e)


# ===========================================================================
# STRUCTURE TOOLS (3 tools)
# ===========================================================================


@mcp.tool()
async def ghome_structures() -> str:
    """List all structures (homes) with their IDs."""
    try:
        structures = await _run(_get_client().list_structures)
        return format_structure_list(structures)
    except GoogleHomeError as e:
        return _error(e)


@mcp.tool()
async def ghome_rooms(
    structure_id: Annotated[str, Field(description="Structure ID from ghome_structures")],
) -> str:
    """List rooms in a structure."""
    try:
        rooms = await _run(_get_client().list_rooms, structure_id)
        return format_room_list(rooms)
    except GoogleHomeError as e:
        return _error(e)


@mcp.tool()
async def ghome_devices(
    device_type: Annotated[
        str | None,
        Field(description="Filter by type: THERMOSTAT, CAMERA, DOORBELL, DISPLAY"),
    ] = None,
) -> str:
    """List all devices. Optional filter by type. Compact one-line-per-device output."""
    try:
        if device_type:
            type_map = {
                "THERMOSTAT": DEVICE_TYPE_THERMOSTAT,
                "CAMERA": DEVICE_TYPE_CAMERA,
                "DOORBELL": DEVICE_TYPE_DOORBELL,
                "DISPLAY": "sdm.devices.types.DISPLAY",
            }
            full_type = type_map.get(device_type.upper(), f"sdm.devices.types.{device_type.upper()}")
            devices = await _run(_get_client().list_devices_by_type, full_type)
        else:
            devices = await _run(_get_client().list_devices)
        return format_device_list(devices)
    except GoogleHomeError as e:
        return _error(e)


# ===========================================================================
# DEVICE DETAIL (1 tool)
# ===========================================================================


@mcp.tool()
async def ghome_device(
    device: Annotated[str, Field(description="Device ID or custom name")],
) -> str:
    """Get full device detail with all traits, status, and capabilities."""
    try:
        found = await _run(_get_client().find_device, device)
        if found is None:
            return f"Error: Device '{device}' not found. Use ghome_devices to list available devices."
        return format_device_detail(found)
    except GoogleHomeError as e:
        return _error(e)


# ===========================================================================
# THERMOSTAT TOOLS (3 tools, write-gated)
# ===========================================================================


@mcp.tool()
async def ghome_thermostat_mode(
    device: Annotated[str, Field(description="Device ID or custom name")],
    mode: Annotated[str, Field(description="Mode: HEAT, COOL, HEATCOOL, or OFF")],
) -> str:
    """Set thermostat mode. Requires GOOGLE_HOME_WRITE_ENABLED=true."""
    gate = require_write()
    if gate:
        return gate
    try:
        found = await _run(_get_client().find_device, device)
        if found is None:
            return f"Error: Device '{device}' not found."
        cmd = build_thermostat_mode_command(mode)
        result = await _run(
            _get_client().execute_command,
            found.device_id,
            cmd["command"],
            cmd.get("params"),
        )
        return f"Set {found.custom_name} mode to {mode.upper()} | {format_command_response(result)}"
    except GoogleHomeError as e:
        return _error(e)


@mcp.tool()
async def ghome_thermostat_setpoint(
    device: Annotated[str, Field(description="Device ID or custom name")],
    heat_celsius: Annotated[float | None, Field(description="Heat setpoint in Celsius")] = None,
    cool_celsius: Annotated[float | None, Field(description="Cool setpoint in Celsius")] = None,
) -> str:
    """Set thermostat temperature target. Provide heat, cool, or both for range mode.

    Requires GOOGLE_HOME_WRITE_ENABLED=true.
    """
    gate = require_write()
    if gate:
        return gate
    if heat_celsius is None and cool_celsius is None:
        return "Error: Provide at least one of heat_celsius or cool_celsius."
    try:
        found = await _run(_get_client().find_device, device)
        if found is None:
            return f"Error: Device '{device}' not found."
        cmd = build_thermostat_setpoint_command(heat_celsius, cool_celsius)
        result = await _run(
            _get_client().execute_command,
            found.device_id,
            cmd["command"],
            cmd.get("params"),
        )
        parts = [f"Set {found.custom_name}"]
        if heat_celsius is not None:
            parts.append(f"heat→{heat_celsius}°C")
        if cool_celsius is not None:
            parts.append(f"cool→{cool_celsius}°C")
        return " ".join(parts) + f" | {format_command_response(result)}"
    except GoogleHomeError as e:
        return _error(e)


@mcp.tool()
async def ghome_thermostat_eco(
    device: Annotated[str, Field(description="Device ID or custom name")],
    eco_mode: Annotated[str, Field(description="MANUAL_ECO to enable, OFF to disable")],
) -> str:
    """Toggle thermostat eco mode. Requires GOOGLE_HOME_WRITE_ENABLED=true."""
    gate = require_write()
    if gate:
        return gate
    try:
        found = await _run(_get_client().find_device, device)
        if found is None:
            return f"Error: Device '{device}' not found."
        cmd = build_thermostat_eco_command(eco_mode)
        result = await _run(
            _get_client().execute_command,
            found.device_id,
            cmd["command"],
            cmd.get("params"),
        )
        return f"Set {found.custom_name} eco={eco_mode.upper()} | {format_command_response(result)}"
    except GoogleHomeError as e:
        return _error(e)


# ===========================================================================
# FAN TOOL (1 tool, write-gated)
# ===========================================================================


@mcp.tool()
async def ghome_fan_set(
    device: Annotated[str, Field(description="Device ID or custom name")],
    timer_mode: Annotated[str, Field(description="ON to start fan timer, OFF to stop")],
    duration_seconds: Annotated[int | None, Field(description="Fan timer duration in seconds")] = None,
) -> str:
    """Set thermostat fan mode and timer. Requires GOOGLE_HOME_WRITE_ENABLED=true."""
    gate = require_write()
    if gate:
        return gate
    try:
        found = await _run(_get_client().find_device, device)
        if found is None:
            return f"Error: Device '{device}' not found."
        cmd = build_fan_command(timer_mode, duration_seconds)
        result = await _run(
            _get_client().execute_command,
            found.device_id,
            cmd["command"],
            cmd.get("params"),
        )
        return f"Set {found.custom_name} fan={timer_mode.upper()} | {format_command_response(result)}"
    except GoogleHomeError as e:
        return _error(e)


# ===========================================================================
# CAMERA TOOLS (2 tools)
# ===========================================================================


@mcp.tool()
async def ghome_camera_stream(
    device: Annotated[str, Field(description="Device ID or custom name")],
    protocol: Annotated[str, Field(description="WEB_RTC (default) or RTSP")] = "WEB_RTC",
) -> str:
    """Generate a camera live stream URL. Stream sessions last 5 minutes.

    Requires GOOGLE_HOME_WRITE_ENABLED=true (generates an authenticated stream).
    """
    gate = require_write()
    if gate:
        return gate
    try:
        found = await _run(_get_client().find_device, device)
        if found is None:
            return f"Error: Device '{device}' not found."
        if found.device_type not in (DEVICE_TYPE_CAMERA, DEVICE_TYPE_DOORBELL):
            return f"Error: {found.custom_name} is not a camera/doorbell."
        cmd = build_camera_stream_command(protocol)
        result = await _run(
            _get_client().execute_command,
            found.device_id,
            cmd["command"],
            cmd.get("params"),
        )
        return f"Stream for {found.custom_name} | {format_command_response(result)}"
    except GoogleHomeError as e:
        return _error(e)


@mcp.tool()
async def ghome_camera_image(
    device: Annotated[str, Field(description="Device ID or custom name")],
    event_id: Annotated[str, Field(description="Event ID from ghome_events")],
) -> str:
    """Get a snapshot image from a camera event. Requires GOOGLE_HOME_WRITE_ENABLED=true."""
    gate = require_write()
    if gate:
        return gate
    try:
        found = await _run(_get_client().find_device, device)
        if found is None:
            return f"Error: Device '{device}' not found."
        cmd = build_camera_image_command(event_id)
        result = await _run(
            _get_client().execute_command,
            found.device_id,
            cmd["command"],
            cmd.get("params"),
        )
        return f"Image for {found.custom_name} | {format_command_response(result)}"
    except GoogleHomeError as e:
        return _error(e)


# ===========================================================================
# GENERIC COMMAND (1 tool, write-gated + confirm-gated)
# ===========================================================================


@mcp.tool()
async def ghome_command(
    device: Annotated[str, Field(description="Device ID or custom name")],
    command: Annotated[str, Field(description="Full SDM command (e.g. sdm.devices.traits.ThermostatMode.SetMode)")],
    params: Annotated[dict[str, Any] | None, Field(description="Command parameters as JSON object")] = None,
    confirm: Annotated[bool, Field(description="Must be true to execute")] = False,
) -> str:
    """Execute any SDM device command. Escape hatch for commands not covered by specific tools.

    Requires GOOGLE_HOME_WRITE_ENABLED=true and confirm=true.
    """
    gate = require_write()
    if gate:
        return gate
    if not confirm:
        return "Error: Set confirm=true to execute raw device commands. Review the command carefully first."
    try:
        found = await _run(_get_client().find_device, device)
        if found is None:
            return f"Error: Device '{device}' not found."
        cmd = build_generic_command(command, params)
        result = await _run(
            _get_client().execute_command,
            found.device_id,
            cmd["command"],
            cmd.get("params"),
        )
        return f"Command on {found.custom_name} | {format_command_response(result)}"
    except GoogleHomeError as e:
        return _error(e)


# ===========================================================================
# EVENT TOOLS (1 tool)
# ===========================================================================


@mcp.tool()
async def ghome_events(
    max_messages: Annotated[int, Field(description="Maximum events to retrieve (1-25)")] = 10,
) -> str:
    """Pull recent device events from Pub/Sub. Requires GOOGLE_HOME_PUBSUB_SUBSCRIPTION configured."""
    try:
        clamped = max(1, min(25, max_messages))
        events = await _run(_get_client().pull_events, clamped)
        return format_events(events)
    except GoogleHomeError as e:
        return _error(e)


# ===========================================================================
# BATCH / CONVENIENCE (2 tools)
# ===========================================================================


@mcp.tool()
async def ghome_status() -> str:
    """Compact status dashboard for all devices. One line per device with key metrics."""
    try:
        devices = await _run(_get_client().list_devices)
        return format_status_dashboard(devices)
    except GoogleHomeError as e:
        return _error(e)


@mcp.tool()
async def ghome_thermostats() -> str:
    """All thermostats at a glance: ambient temp, setpoint, mode, HVAC status."""
    try:
        devices = await _run(_get_client().list_devices_by_type, DEVICE_TYPE_THERMOSTAT)
        return format_thermostat_list(devices)
    except GoogleHomeError as e:
        return _error(e)


# ===========================================================================
# Entry point
# ===========================================================================


def main() -> None:
    """Run the MCP server."""
    if TRANSPORT == "http":
        from google_home_blade_mcp.auth import BearerAuthMiddleware

        mcp.settings.http_app_kwargs = {"middleware": [BearerAuthMiddleware]}
        mcp.run(transport="streamable-http", host=HTTP_HOST, port=HTTP_PORT)
    else:
        mcp.run(transport="stdio")
