"""Shared test fixtures for Google Home Blade MCP tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from google_home_blade_mcp.models import (
    DEVICE_TYPE_CAMERA,
    DEVICE_TYPE_DOORBELL,
    DEVICE_TYPE_THERMOSTAT,
    TRAIT_PREFIX,
    DeviceInfo,
    GoogleHomeConfig,
    RoomInfo,
    StructureInfo,
)


@pytest.fixture
def config() -> GoogleHomeConfig:
    """Test configuration."""
    return GoogleHomeConfig(
        client_id="test-client-id",
        client_secret="test-client-secret",
        refresh_token="test-refresh-token",
        project_id="test-project-id",
        write_enabled=False,
    )


@pytest.fixture
def write_config() -> GoogleHomeConfig:
    """Test configuration with writes enabled."""
    return GoogleHomeConfig(
        client_id="test-client-id",
        client_secret="test-client-secret",
        refresh_token="test-refresh-token",
        project_id="test-project-id",
        write_enabled=True,
    )


# ---------------------------------------------------------------------------
# Device fixtures
# ---------------------------------------------------------------------------


def make_thermostat(
    device_id: str = "thermostat-1",
    name: str = "Living Room",
    room: str = "Living Room",
    ambient_c: float = 21.5,
    humidity: int = 45,
    mode: str = "HEAT",
    heat_setpoint: float = 22.0,
    hvac_status: str = "HEATING",
    online: bool = True,
) -> DeviceInfo:
    """Create a mock thermostat DeviceInfo."""
    return DeviceInfo(
        name=f"enterprises/test-project/devices/{device_id}",
        device_type=DEVICE_TYPE_THERMOSTAT,
        traits={
            f"{TRAIT_PREFIX}Info": {"customName": name},
            f"{TRAIT_PREFIX}Connectivity": {"status": "ONLINE" if online else "OFFLINE"},
            f"{TRAIT_PREFIX}Temperature": {"ambientTemperatureCelsius": ambient_c},
            f"{TRAIT_PREFIX}Humidity": {"ambientHumidityPercent": humidity},
            f"{TRAIT_PREFIX}ThermostatMode": {"mode": mode, "availableModes": ["HEAT", "COOL", "HEATCOOL", "OFF"]},
            f"{TRAIT_PREFIX}ThermostatTemperatureSetpoint": {"heatCelsius": heat_setpoint},
            f"{TRAIT_PREFIX}ThermostatEco": {"mode": "OFF", "heatCelsius": 15.5, "coolCelsius": 28.0},
            f"{TRAIT_PREFIX}ThermostatHvac": {"status": hvac_status},
            f"{TRAIT_PREFIX}Settings": {"temperatureScale": "CELSIUS"},
        },
        parent_relations=[{"parent": "enterprises/test-project/structures/struct-1/rooms/room-1", "displayName": room}],
    )


def make_camera(
    device_id: str = "camera-1",
    name: str = "Front Door Camera",
    room: str = "Entry",
    online: bool = True,
    has_motion: bool = True,
    has_person: bool = True,
    has_sound: bool = False,
) -> DeviceInfo:
    """Create a mock camera DeviceInfo."""
    traits: dict[str, dict[str, object]] = {
        f"{TRAIT_PREFIX}Info": {"customName": name},
        f"{TRAIT_PREFIX}Connectivity": {"status": "ONLINE" if online else "OFFLINE"},
        f"{TRAIT_PREFIX}CameraLiveStream": {
            "supportedProtocols": ["WEB_RTC"],
            "maxVideoResolution": {"width": 1920, "height": 1080},
        },
    }
    if has_motion:
        traits[f"{TRAIT_PREFIX}CameraMotion"] = {}
    if has_person:
        traits[f"{TRAIT_PREFIX}CameraPerson"] = {}
    if has_sound:
        traits[f"{TRAIT_PREFIX}CameraSound"] = {}

    return DeviceInfo(
        name=f"enterprises/test-project/devices/{device_id}",
        device_type=DEVICE_TYPE_CAMERA,
        traits=traits,
        parent_relations=[{"parent": "enterprises/test-project/structures/struct-1/rooms/room-2", "displayName": room}],
    )


def make_doorbell(
    device_id: str = "doorbell-1",
    name: str = "Front Door",
    room: str = "Entry",
    online: bool = True,
) -> DeviceInfo:
    """Create a mock doorbell DeviceInfo."""
    return DeviceInfo(
        name=f"enterprises/test-project/devices/{device_id}",
        device_type=DEVICE_TYPE_DOORBELL,
        traits={
            f"{TRAIT_PREFIX}Info": {"customName": name},
            f"{TRAIT_PREFIX}Connectivity": {"status": "ONLINE" if online else "OFFLINE"},
            f"{TRAIT_PREFIX}CameraLiveStream": {"supportedProtocols": ["WEB_RTC"]},
            f"{TRAIT_PREFIX}CameraMotion": {},
            f"{TRAIT_PREFIX}CameraPerson": {},
            f"{TRAIT_PREFIX}DoorbellChime": {},
        },
        parent_relations=[{"parent": "enterprises/test-project/structures/struct-1/rooms/room-3", "displayName": room}],
    )


def make_structure(
    structure_id: str = "struct-1",
    name: str = "My Home",
) -> StructureInfo:
    """Create a mock StructureInfo."""
    return StructureInfo(
        name=f"enterprises/test-project/structures/{structure_id}",
        display_name=name,
    )


def make_room(
    room_id: str = "room-1",
    name: str = "Living Room",
) -> RoomInfo:
    """Create a mock RoomInfo."""
    return RoomInfo(
        name=f"enterprises/test-project/structures/struct-1/rooms/{room_id}",
        display_name=name,
    )


@pytest.fixture
def thermostat() -> DeviceInfo:
    return make_thermostat()


@pytest.fixture
def camera() -> DeviceInfo:
    return make_camera()


@pytest.fixture
def doorbell() -> DeviceInfo:
    return make_doorbell()


@pytest.fixture
def structure() -> StructureInfo:
    return make_structure()


@pytest.fixture
def room() -> RoomInfo:
    return make_room()


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock GoogleHomeClient."""
    client = MagicMock()
    client.info.return_value = {
        "status": "ok",
        "project_id": "test-project",
        "structures": 1,
        "devices": 3,
        "device_types": {"Thermostat": 1, "Camera": 1, "Doorbell": 1},
        "write_enabled": False,
        "pubsub_configured": False,
    }
    client.list_devices.return_value = [make_thermostat(), make_camera(), make_doorbell()]
    client.list_structures.return_value = [make_structure()]
    client.list_rooms.return_value = [make_room(), make_room("room-2", "Entry")]
    client.find_device.return_value = make_thermostat()
    client.list_devices_by_type.return_value = [make_thermostat()]
    client.execute_command.return_value = {"results": {}}
    client.pull_events.return_value = []
    return client
