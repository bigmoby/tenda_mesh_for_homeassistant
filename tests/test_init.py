"""Tests for Tenda Mesh integration setup."""

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tenda_mesh.const import DOMAIN


@pytest.mark.asyncio
async def test_setup_unload_entry(hass: HomeAssistant) -> None:
    """Test setting up and unloading a config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "192.168.1.1",
            "username": "admin",
            "password": "password",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.tenda_mesh.api.TendaLocalClient.ensure_authenticated",
            AsyncMock(),
        ),
        patch(
            "custom_components.tenda_mesh.api.TendaLocalClient.get_modules",
            AsyncMock(
                return_value={
                    "wanStatus": {
                        "wanType": "dhcp",
                        "connectStatus": "connected",
                        "wanIP": "1.1.1.1",
                    },
                    "meshTopo": [{"sn": "r1", "mac": "r1", "nodeType": "controller"}],
                    "deviceList": [{"onlineList": []}],
                    "wifiBasicCfg": {"wifiEn": True, "wifiSSID": "test"},
                }
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id) is True
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED

        assert await hass.config_entries.async_unload(entry.entry_id) is True
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
