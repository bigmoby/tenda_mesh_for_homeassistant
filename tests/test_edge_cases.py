"""Tests for Tenda Mesh edge cases to improve coverage."""

from unittest.mock import patch

from homeassistant import data_entry_flow
from homeassistant.core import HomeAssistant
import pytest

from custom_components.tenda_mesh.api import (
    TendaAuthError,
    TendaConnectionError,
    TendaLocalClient,
)
from custom_components.tenda_mesh.const import DOMAIN


@pytest.mark.asyncio
async def test_config_flow_unknown_error(hass: HomeAssistant):
    """Test config flow handles unexpected exceptions."""
    user_input = {
        "host": "1.1.1.1",
        "username": "admin",
        "password": "password",
    }

    with patch(
        "custom_components.tenda_mesh.api.TendaLocalClient.test_connection",
        side_effect=Exception("Unexpected"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data=user_input
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["errors"]["base"] == "unknown"


@pytest.mark.asyncio
async def test_reconfigure_flow_errors(hass: HomeAssistant):
    """Test reconfigure flow handles errors."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": "1.1.1.1"}, entry_id="test_reconfig"
    )
    entry.add_to_hass(hass)

    user_input = {
        "host": "1.1.1.1",
        "username": "admin",
        "password": "password",
    }

    # Test Auth Error
    with patch(
        "custom_components.tenda_mesh.api.TendaLocalClient.test_connection",
        side_effect=TendaAuthError("fail"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry.entry_id},
            data=user_input,
        )
        assert result["errors"]["base"] == "invalid_auth"

    # Test Connection Error
    with patch(
        "custom_components.tenda_mesh.api.TendaLocalClient.test_connection",
        side_effect=TendaConnectionError("fail"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry.entry_id},
            data=user_input,
        )
        assert result["errors"]["base"] == "cannot_connect"

    # Test Unknown Error
    with patch(
        "custom_components.tenda_mesh.api.TendaLocalClient.test_connection",
        side_effect=Exception("fail"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry.entry_id},
            data=user_input,
        )
        assert result["errors"]["base"] == "unknown"


@pytest.mark.asyncio
async def test_api_test_connection_fail():
    """Test client.test_connection failure."""
    client = TendaLocalClient("1.1.1.1", "u", "p")

    with (
        patch.object(
            client, "ensure_authenticated", side_effect=TendaAuthError("fail")
        ),
        pytest.raises(TendaAuthError),
    ):
        await client.test_connection()

    with (
        patch.object(
            client, "ensure_authenticated", side_effect=TendaConnectionError("fail")
        ),
        pytest.raises(TendaConnectionError),
    ):
        await client.test_connection()
