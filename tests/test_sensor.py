"""Tests for Tenda Mesh sensors."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tenda_mesh.api import TendaLocalClient
from custom_components.tenda_mesh.const import COORDINATOR, DOMAIN
from custom_components.tenda_mesh.coordinator import TendaMeshCoordinator
from custom_components.tenda_mesh.sensor import async_setup_entry


@pytest.fixture
def mock_client():
    """Mock Tenda API client."""
    client = MagicMock(spec=TendaLocalClient)
    client.host = "192.168.1.1"
    client.ensure_authenticated = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_sensors(hass: HomeAssistant, mock_client) -> None:
    """Test sensor setup and values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "192.168.1.1",
            "username": "admin",
            "password": "password",
        },
        entry_id="test_entry_sensor",
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    # Mock coordinator data
    mock_client.get_modules = AsyncMock(
        return_value={
            "wanStatus": {
                "wanType": "dhcp",
                "connectStatus": "connected",
                "wanIP": "1.2.3.4",
            },
            "meshTopo": [
                {
                    "sn": "r1",
                    "mac": "r1",
                    "nodeType": "controller",
                    "connectStatus": "Excellent",
                    "connectTime": "500",
                }
            ],
            "deviceList": [
                {
                    "onlineList": [
                        {
                            "mac": "m1",
                            "connectTime": "100",
                            "hostname": "Dev1",
                            "ip": "1.1.1.1",
                            "connectType": "5G",
                        }
                    ]
                }
            ],
        }
    )

    coordinator = TendaMeshCoordinator(hass, mock_client, entry=entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN] = {entry.entry_id: {COORDINATOR: coordinator}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)

    assert async_add_entities.called
    entities = async_add_entities.call_args[0][0]

    # Sensor names: "WAN IP Address", "WAN Status", "Total Connected Clients",
    # plus per-node sensors like "Uptime", "Connected Clients", etc.

    # Test WAN IP Address sensor
    wan_ip = next((e for e in entities if "WAN IP" in e.name), None)
    assert wan_ip is not None
    assert wan_ip.native_value == "1.2.3.4"

    # Test WAN Status sensor
    wan_status = next((e for e in entities if e.name == "WAN Status"), None)
    assert wan_status is not None
    assert wan_status.native_value == "connected"

    # Test Total Connected Clients
    total = next((e for e in entities if "Total Connected" in e.name), None)
    assert total is not None

    # Test per-node Uptime sensor
    node_uptime = next(
        (e for e in entities if "Uptime" in e.name and "r1" in e.unique_id), None
    )
    assert node_uptime is not None
    assert isinstance(node_uptime.native_value, datetime)

    # Test edge case: missing data
    coordinator.data = {}
    assert wan_ip.native_value is None
    assert node_uptime.native_value is None
