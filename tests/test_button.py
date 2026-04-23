"""Tests for Tenda Mesh buttons."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tenda_mesh.api import TendaConnectionError, TendaLocalClient
from custom_components.tenda_mesh.button import async_setup_entry
from custom_components.tenda_mesh.const import COORDINATOR, DOMAIN
from custom_components.tenda_mesh.coordinator import TendaMeshCoordinator


@pytest.fixture
def mock_client():
    """Mock Tenda API client."""
    client = MagicMock(spec=TendaLocalClient)
    client.host = "192.168.1.1"
    client.ensure_authenticated = AsyncMock()
    client.set_modules = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_buttons(hass: HomeAssistant, mock_client) -> None:
    """Test button setup and press."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "192.168.1.1",
            "username": "admin",
            "password": "password",
        },
        entry_id="test_entry_button",
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    # Mock coordinator data
    mock_client.get_modules = AsyncMock(
        return_value={
            "meshTopo": [
                {
                    "sn": "router1",
                    "mac": "AA:BB:CC:DD:EE:01",
                    "nodeType": "controller",
                    "nodeName": "Main Router",
                    "softVersion": "1.0.0",
                },
                {
                    # Node with missing MAC to test skip logic
                    "sn": "router2",
                },
            ],
        }
    )

    coordinator = TendaMeshCoordinator(hass, mock_client, entry=entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN] = {entry.entry_id: {COORDINATOR: coordinator}}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)

    assert async_add_entities.called
    buttons = async_add_entities.call_args[0][0]

    # Check network reboot button
    reboot_net = next(
        b for b in buttons if b.entity_description.key == "reboot_network"
    )
    assert reboot_net.device_info["identifiers"] == {(DOMAIN, entry.entry_id)}
    await reboot_net.async_press()
    mock_client.set_modules.assert_any_call(["systemReboot"], {"systemReboot": {}})

    # Check node reboot button
    reboot_node = next(
        b
        for b in buttons
        if b.entity_description.key == "reboot_node" and b._mac == "router1"
    )
    assert reboot_node.device_info["identifiers"] == {(DOMAIN, "router1")}
    await reboot_node.async_press()
    # The payload for node reboot should include sn/mac/ip
    mock_client.set_modules.assert_any_call(
        ["systemReboot"], {"systemReboot": {"sn": "router1", "mac": "", "ip": ""}}
    )

    # Test failure during press
    mock_client.set_modules.side_effect = Exception("reboot failed")
    with patch("custom_components.tenda_mesh.button._LOGGER.error") as mock_log:
        await reboot_net.async_press()
        assert mock_log.called

    # Test node not found during press
    reboot_node._mac = "non_existent"
    with patch("custom_components.tenda_mesh.button._LOGGER.error") as mock_log:
        await reboot_node.async_press()
        assert mock_log.called

    # Test Server disconnected during press
    mock_client.set_modules.side_effect = TendaConnectionError("Server disconnected")
    with patch("custom_components.tenda_mesh.button._LOGGER.info") as mock_log:
        await reboot_net.async_press()
        # Should log info "Reboot command sent, connection closed as expected"
        assert any(
            "connection closed as expected" in call.args[0]
            for call in mock_log.call_args_list
        )
