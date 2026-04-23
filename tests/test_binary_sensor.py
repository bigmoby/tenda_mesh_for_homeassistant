"""Tests for Tenda Mesh binary sensors."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tenda_mesh.api import TendaLocalClient
from custom_components.tenda_mesh.binary_sensor import async_setup_entry
from custom_components.tenda_mesh.const import COORDINATOR, DOMAIN
from custom_components.tenda_mesh.coordinator import TendaMeshCoordinator


@pytest.fixture
def mock_client():
    """Mock Tenda API client."""
    client = MagicMock(spec=TendaLocalClient)
    client.host = "192.168.1.1"
    client.ensure_authenticated = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_binary_sensors(hass: HomeAssistant, mock_client) -> None:
    """Test binary sensor setup and values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "192.168.1.1",
            "username": "admin",
            "password": "password",
        },
        entry_id="test_entry_binary",
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
            "meshTopo": [{"sn": "r1", "mac": "r1", "nodeType": "controller"}],
            "deviceList": [{"onlineList": []}],
        }
    )

    coordinator = TendaMeshCoordinator(hass, mock_client, entry=entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN] = {entry.entry_id: {COORDINATOR: coordinator}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)

    assert async_add_entities.called
    entities = async_add_entities.call_args[0][0]

    # binary sensors are per-node connectivity sensors
    node_sensor = next((e for e in entities if e._mac == "r1"), None)
    assert node_sensor is not None
    assert node_sensor.is_on is True

    # Test node disconnected
    coordinator.data["nodes"][0]["online"] = False
    assert node_sensor.is_on is False

    # Test missing data
    coordinator.data = {}
    assert node_sensor.is_on is None
