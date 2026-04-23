"""Config flow for Tenda Mesh integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import TendaAuthError, TendaConnectionError, TendaLocalClient
from .const import DEFAULT_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class TendaMeshConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the UI-driven configuration flow for Tenda Mesh."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            username = user_input.get(CONF_USERNAME, DEFAULT_USERNAME).strip()
            password = user_input[CONF_PASSWORD]

            # Prevent duplicate entries for the same router
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            # Validate connectivity
            session = async_get_clientsession(self.hass)
            client = TendaLocalClient(
                host=host,
                username=username,
                password=password,
                session=session,
            )

            try:
                await client.test_connection()
            except TendaAuthError:
                errors["base"] = "invalid_auth"
            except TendaConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Tenda Mesh ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow the user to update credentials/settings after initial setup."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            username = user_input.get(CONF_USERNAME, DEFAULT_USERNAME).strip()
            password = user_input[CONF_PASSWORD]

            session = async_get_clientsession(self.hass)
            client = TendaLocalClient(
                host=host,
                username=username,
                password=password,
                session=session,
            )
            try:
                await client.test_connection()
            except TendaAuthError:
                errors["base"] = "invalid_auth"
            except TendaConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during reconfigure test")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                vol.Optional(
                    CONF_USERNAME,
                    default=entry.data.get(CONF_USERNAME, DEFAULT_USERNAME),
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )
