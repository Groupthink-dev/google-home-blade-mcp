"""Tests for models, config, exceptions, and credential scrubbing."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from google_home_blade_mcp.models import (
    AuthError,
    CommandError,
    ConfigError,
    DeviceInfo,
    GoogleHomeConfig,
    GoogleHomeError,
    NotFoundError,
    RateLimitError,
    RoomInfo,
    StructureInfo,
    _scrub_credentials,
    classify_error,
    is_write_enabled,
    require_write,
)


class TestGoogleHomeConfig:
    def test_from_env_success(self) -> None:
        env = {
            "GOOGLE_HOME_CLIENT_ID": "cid",
            "GOOGLE_HOME_CLIENT_SECRET": "csec",
            "GOOGLE_HOME_REFRESH_TOKEN": "rtok",
            "GOOGLE_HOME_PROJECT_ID": "pid",
            "GOOGLE_HOME_WRITE_ENABLED": "true",
            "GOOGLE_HOME_PUBSUB_SUBSCRIPTION": "projects/p/subscriptions/s",
        }
        with patch.dict(os.environ, env, clear=False):
            config = GoogleHomeConfig.from_env()
            assert config.client_id == "cid"
            assert config.client_secret == "csec"
            assert config.refresh_token == "rtok"
            assert config.project_id == "pid"
            assert config.write_enabled is True
            assert config.pubsub_subscription == "projects/p/subscriptions/s"

    def test_from_env_missing_required(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigError, match="Missing required"):
                GoogleHomeConfig.from_env()

    def test_write_enabled_defaults_false(self) -> None:
        env = {
            "GOOGLE_HOME_CLIENT_ID": "c",
            "GOOGLE_HOME_CLIENT_SECRET": "s",
            "GOOGLE_HOME_REFRESH_TOKEN": "r",
            "GOOGLE_HOME_PROJECT_ID": "p",
        }
        with patch.dict(os.environ, env, clear=False):
            config = GoogleHomeConfig.from_env()
            assert config.write_enabled is False


class TestWriteGate:
    def test_write_disabled(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_HOME_WRITE_ENABLED": "false"}):
            assert is_write_enabled() is False
            result = require_write()
            assert result is not None
            assert "disabled" in result.lower()

    def test_write_enabled(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_HOME_WRITE_ENABLED": "true"}):
            assert is_write_enabled() is True
            assert require_write() is None


class TestErrorClassification:
    @pytest.mark.parametrize(
        "message,expected_type",
        [
            ("401 Unauthorized", AuthError),
            ("UNAUTHENTICATED: token expired", AuthError),
            ("invalid_grant: token revoked", AuthError),
            ("403 Forbidden", AuthError),
            ("404 Not Found", NotFoundError),
            ("NOT_FOUND: device does not exist", NotFoundError),
            ("Rate limit exceeded", RateLimitError),
            ("RESOURCE_EXHAUSTED: quota", RateLimitError),
            ("Command failed: device offline", CommandError),
            ("FAILED_PRECONDITION: mode conflict", CommandError),
            ("Unknown error occurred", GoogleHomeError),
        ],
    )
    def test_classify_error(self, message: str, expected_type: type) -> None:
        err = classify_error(message)
        assert isinstance(err, expected_type)


class TestCredentialScrubbing:
    def test_scrub_access_token(self) -> None:
        text = "access_token: ya29.a0AfH6SMBx1234567890abcdef"
        result = _scrub_credentials(text)
        assert "ya29.a0AfH6SMBx" not in result
        assert "****" in result

    def test_scrub_bearer(self) -> None:
        text = "Authorization: Bearer ya29.token123"
        result = _scrub_credentials(text)
        assert "ya29.token123" not in result

    def test_scrub_refresh_token(self) -> None:
        text = "refresh_token=1//0abc_defGHI"
        result = _scrub_credentials(text)
        assert "1//0abc" not in result

    def test_no_scrub_clean_text(self) -> None:
        text = "Device not found in structure"
        assert _scrub_credentials(text) == text


class TestDeviceInfo:
    def test_from_api(self) -> None:
        data = {
            "name": "enterprises/proj/devices/dev1",
            "type": "sdm.devices.types.THERMOSTAT",
            "traits": {
                "sdm.devices.traits.Info": {"customName": "Living Room"},
                "sdm.devices.traits.Connectivity": {"status": "ONLINE"},
            },
            "parentRelations": [{"parent": "enterprises/proj/structures/s1/rooms/r1", "displayName": "Lounge"}],
        }
        device = DeviceInfo.from_api(data)
        assert device.device_id == "dev1"
        assert device.type_label == "Thermostat"
        assert device.custom_name == "Living Room"
        assert device.room_name == "Lounge"
        assert device.is_online is True

    def test_offline_device(self) -> None:
        data = {
            "name": "enterprises/proj/devices/dev2",
            "type": "sdm.devices.types.CAMERA",
            "traits": {"sdm.devices.traits.Connectivity": {"status": "OFFLINE"}},
        }
        device = DeviceInfo.from_api(data)
        assert device.is_online is False
        assert device.custom_name == "dev2"  # Falls back to device ID
        assert device.room_name is None

    def test_unknown_type_label(self) -> None:
        data = {
            "name": "enterprises/proj/devices/dev3",
            "type": "sdm.devices.types.UNKNOWN_WIDGET",
            "traits": {},
        }
        device = DeviceInfo.from_api(data)
        assert device.type_label == "UNKNOWN_WIDGET"


class TestStructureInfo:
    def test_from_api(self) -> None:
        data = {
            "name": "enterprises/proj/structures/s1",
            "traits": {"sdm.devices.traits.Info": {"customName": "Beach House"}},
        }
        struct = StructureInfo.from_api(data)
        assert struct.structure_id == "s1"
        assert struct.display_name == "Beach House"


class TestRoomInfo:
    def test_from_api(self) -> None:
        data = {
            "name": "enterprises/proj/structures/s1/rooms/r1",
            "traits": {"sdm.devices.traits.Info": {"customName": "Kitchen"}},
        }
        room = RoomInfo.from_api(data)
        assert room.room_id == "r1"
        assert room.display_name == "Kitchen"
