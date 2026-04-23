"""Tests for the Tenda Mesh coordinator."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.tenda_mesh.api import (
    TendaAuthError,
    TendaConnectionError,
    TendaLocalClient,
)
from custom_components.tenda_mesh.coordinator import TendaMeshCoordinator


@pytest.fixture
def mock_client():
    """Mock Tenda API client."""
    client = MagicMock(spec=TendaLocalClient)
    client.host = "192.168.1.1"
    client.ensure_authenticated = AsyncMock()
    client.get_modules = AsyncMock()
    client.stok = "1234"
    client.sign = "1234567890123456"
    return client


@pytest.mark.asyncio
async def test_coordinator_update(hass, mock_client):
    """Test coordinator data update."""
    mock_client.get_modules.return_value = {
        "wanStatus": {
            "wanType": "dhcp",
            "connectStatus": "connected",
            "wanIP": "1.2.3.4",
        },
        "meshTopo": [
            {
                "sn": "router1",
                "mac": "AA:BB:CC:DD:EE:01",
                "nodeType": "controller",
                "connectStatus": "Excellent",
                "nodeName": "Main",
                "connectTime": "1000",
                "linkRate": "1000",
                "hop": "0",
                "childNode": [
                    {
                        "sn": "router2",
                        "mac": "AA:BB:CC:DD:EE:02",
                        "nodeType": "slave",
                        "connectStatus": "Disconnected",
                        "nodeName": "Satellite",
                    }
                ],
            }
        ],
        "deviceList": [
            {
                "onlineList": [
                    {
                        "mac": "11:22:33:44:55:66",
                        "hostname": "PC1",
                        "ip": "192.168.1.100",
                        "connectType": "5G",
                        "connectTime": "500",
                        "devType": "PC",
                        "accessNode": {
                            "sn": "router1",
                            "ip": "192.168.1.1",
                            "mac": "AA:BB:CC:DD:EE:01",
                        },
                    }
                ]
            }
        ],
    }

    coordinator = TendaMeshCoordinator(hass, mock_client)
    data = await coordinator._async_update_data()

    assert data["wan"]["type"] == "dhcp"
    assert any(n["mac"] == "router1" for n in data["nodes"])
    assert any(n["mac"] == "router2" for n in data["nodes"])
    assert data["devices"]["11:22:33:44:55:66"]["name"] == "PC1"

    # Verify enrichment
    router1 = next(n for n in data["nodes"] if n["mac"] == "router1")
    assert router1["ip"] == "192.168.1.1"
    assert router1["client_list"][0]["mac"] == "11:22:33:44:55:66"


@pytest.mark.asyncio
async def test_coordinator_auth_failure(hass, mock_client):
    """Test coordinator handles auth failure and re-auth."""
    coordinator = TendaMeshCoordinator(hass, mock_client)

    # First call fails with TendaAuthError
    mock_client.get_modules.side_effect = [TendaAuthError("expired"), {"success": True}]

    await coordinator._async_update_data()
    assert mock_client.ensure_authenticated.call_count == 2
    assert mock_client.stok is None

    # Re-auth also fails
    mock_client.get_modules.side_effect = TendaAuthError("expired")
    mock_client.ensure_authenticated.side_effect = TendaAuthError("failed")
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_connection_error(hass, mock_client):
    """Test coordinator handles connection error."""
    coordinator = TendaMeshCoordinator(hass, mock_client)
    mock_client.get_modules.side_effect = TendaConnectionError("timeout")

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_parse_edge_cases(hass, mock_client):
    """Test parsing edge cases."""
    coordinator = TendaMeshCoordinator(hass, mock_client)

    # Test invalid raw data
    assert coordinator._parse(None) == {}
    assert coordinator._parse([]) == {}

    # Test topology flattening skip
    raw = {"meshTopo": [{"sn": "router1"}]}
    data = coordinator._parse(raw)
    assert any(n["mac"] == "router1" for n in data["nodes"])

    # Test device list variations
    raw = {"deviceList": [{"onlineList": None}, {"onlineList": []}]}
    data = coordinator._parse(raw)
    assert data["devices"] == {}

    # Test SSID parsing
    raw = {
        "wifiBasicCfg": {
            "wifiEn": True,
            "wifiSSID": "2.4",
            "wifiEn_5g": True,
            "wifiSSID_5g": "5",
            "wifiEn_6g": True,
            "wifiSSID_6g": "6",
        }
    }
    data = coordinator._parse(raw)
    assert data["ssids"]["2.4G"] == "2.4"
    assert data["ssids"]["5G"] == "5"
    assert data["ssids"]["6G"] == "6"
