"""Tests for the SDM API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from google_home_blade_mcp.client import GoogleHomeClient
from google_home_blade_mcp.models import (
    AuthError,
    GoogleHomeConfig,
    NotFoundError,
)


@pytest.fixture
def client_config() -> GoogleHomeConfig:
    return GoogleHomeConfig(
        client_id="cid",
        client_secret="csec",
        refresh_token="rtok",
        project_id="test-project",
        write_enabled=True,
    )


@pytest.fixture
def mock_token_manager() -> MagicMock:
    tm = MagicMock()
    tm.get_access_token.return_value = "ya29.mock_token"
    return tm


class TestGoogleHomeClient:
    def test_list_devices(self, client_config: GoogleHomeConfig, mock_token_manager: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "devices": [
                {
                    "name": "enterprises/test-project/devices/dev1",
                    "type": "sdm.devices.types.THERMOSTAT",
                    "traits": {
                        "sdm.devices.traits.Info": {"customName": "Living Room"},
                        "sdm.devices.traits.Connectivity": {"status": "ONLINE"},
                    },
                    "parentRelations": [],
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        client = GoogleHomeClient(client_config)
        client._token_manager = mock_token_manager

        with patch.object(client._http, "get", return_value=mock_response):
            devices = client.list_devices()
            assert len(devices) == 1
            assert devices[0].custom_name == "Living Room"

    def test_list_structures(self, client_config: GoogleHomeConfig, mock_token_manager: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "structures": [
                {
                    "name": "enterprises/test-project/structures/s1",
                    "traits": {"sdm.devices.traits.Info": {"customName": "My Home"}},
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        client = GoogleHomeClient(client_config)
        client._token_manager = mock_token_manager

        with patch.object(client._http, "get", return_value=mock_response):
            structures = client.list_structures()
            assert len(structures) == 1
            assert structures[0].display_name == "My Home"

    def test_execute_command(self, client_config: GoogleHomeConfig, mock_token_manager: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": {}}
        mock_response.raise_for_status = MagicMock()

        client = GoogleHomeClient(client_config)
        client._token_manager = mock_token_manager

        with patch.object(client._http, "post", return_value=mock_response):
            result = client.execute_command("dev1", "sdm.devices.traits.ThermostatMode.SetMode", {"mode": "HEAT"})
            assert result == {"results": {}}

    def test_401_invalidates_token(self, client_config: GoogleHomeConfig, mock_token_manager: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )

        client = GoogleHomeClient(client_config)
        client._token_manager = mock_token_manager

        with patch.object(client._http, "get", return_value=mock_response):
            with pytest.raises(AuthError):
                client.list_devices()
            mock_token_manager.invalidate.assert_called_once()

    def test_404_raises_not_found(self, client_config: GoogleHomeConfig, mock_token_manager: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )

        client = GoogleHomeClient(client_config)
        client._token_manager = mock_token_manager

        with patch.object(client._http, "get", return_value=mock_response):
            with pytest.raises(NotFoundError):
                client.get_device("nonexistent")

    def test_find_device_by_name(self, client_config: GoogleHomeConfig, mock_token_manager: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "devices": [
                {
                    "name": "enterprises/test-project/devices/dev1",
                    "type": "sdm.devices.types.THERMOSTAT",
                    "traits": {"sdm.devices.traits.Info": {"customName": "Living Room"}},
                    "parentRelations": [],
                },
                {
                    "name": "enterprises/test-project/devices/dev2",
                    "type": "sdm.devices.types.CAMERA",
                    "traits": {"sdm.devices.traits.Info": {"customName": "Front Door"}},
                    "parentRelations": [],
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()

        client = GoogleHomeClient(client_config)
        client._token_manager = mock_token_manager

        with patch.object(client._http, "get", return_value=mock_response):
            found = client.find_device("living room")  # case-insensitive
            assert found is not None
            assert found.custom_name == "Living Room"

            not_found = client.find_device("nonexistent")
            assert not_found is None

    def test_info_returns_summary(self, client_config: GoogleHomeConfig, mock_token_manager: MagicMock) -> None:
        devices_response = MagicMock()
        devices_response.json.return_value = {
            "devices": [
                {
                    "name": "enterprises/test-project/devices/dev1",
                    "type": "sdm.devices.types.THERMOSTAT",
                    "traits": {},
                    "parentRelations": [],
                }
            ]
        }
        devices_response.raise_for_status = MagicMock()

        structures_response = MagicMock()
        structures_response.json.return_value = {
            "structures": [{"name": "enterprises/test-project/structures/s1", "traits": {}}]
        }
        structures_response.raise_for_status = MagicMock()

        client = GoogleHomeClient(client_config)
        client._token_manager = mock_token_manager

        call_count = 0

        def mock_get(url: str, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if "structures" in url:
                return structures_response
            return devices_response

        with patch.object(client._http, "get", side_effect=mock_get):
            info = client.info()
            assert info["status"] == "ok"
            assert info["structures"] == 1
            assert info["devices"] == 1
            assert info["device_types"]["Thermostat"] == 1

    def test_info_auth_error(self, client_config: GoogleHomeConfig, mock_token_manager: MagicMock) -> None:
        mock_token_manager.get_access_token.side_effect = AuthError("bad token")

        client = GoogleHomeClient(client_config)
        client._token_manager = mock_token_manager

        info = client.info()
        assert info["status"] == "auth_error"
