"""Tests for Tenda Mesh device trackers."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tenda_mesh.api import TendaLocalClient
from custom_components.tenda_mesh.const import COORDINATOR, DOMAIN
from custom_components.tenda_mesh.coordinator import TendaMeshCoordinator
from custom_components.tenda_mesh.device_tracker import async_setup_entry


@pytest.fixture
def mock_client():
    """Mock Tenda API client."""
    client = MagicMock(spec=TendaLocalClient)
    client.host = "192.168.1.1"
    client.ensure_authenticated = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_device_trackers(hass: HomeAssistant, mock_client) -> None:
    """Test device tracker setup and values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "192.168.1.1",
            "username": "admin",
            "password": "password",
        },
        entry_id="test_entry_tracker",
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    # Mock coordinator data
    mock_client.get_modules = AsyncMock(
        return_value={
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

    tracker = next(e for e in entities if e._mac == "11:22:33:44:55:66")
    assert tracker.is_connected is True
    assert tracker.ip_address == "192.168.1.100"

    # Test property fallbacks
    coordinator.data["devices"]["11:22:33:44:55:66"]["ip"] = None
    assert tracker.ip_address is None

    coordinator.data["devices"]["11:22:33:44:55:66"]["name"] = ""
    # In device_tracker.py: hostname returns None if name is empty
    assert tracker.hostname is None
    # But name property returns the MAC
    assert tracker.name == "11:22:33:44:55:66"

    # Test device offline
    coordinator.data["devices"] = {}
    assert tracker.is_connected is False

    # Test coordinator data empty
    coordinator.data = {}
    assert tracker.is_connected is False

    # Test more attributes
    coordinator.data = {
        "devices": {
            "11:22:33:44:55:66": {
                "name": "PC1",
                "ip": "1.1.1.1",
                "online": True,
                "connection": "Wired",
                "uptime": 1000,
            }
        }
    }
    assert tracker.is_connected is True
    assert tracker.extra_state_attributes["connection_type"] == "Wired"
    # Fixed attribute name
    assert tracker.extra_state_attributes["uptime_seconds"] == 1000
