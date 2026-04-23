"""Button platform for Tenda Mesh."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import TendaConnectionError
from .const import COORDINATOR, DOMAIN
from .coordinator import TendaMeshCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tenda Mesh buttons."""
    coordinator: TendaMeshCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    buttons: list[ButtonEntity] = []

    # System-wide reboot button
    buttons.append(
        TendaMeshRebootButton(
            coordinator,
            mac="mesh_network",
            description=ButtonEntityDescription(
                key="reboot_network",
                name="Reboot Mesh Network",
                icon="mdi:restart",
            ),
            is_global=True,
        )
    )

    # Node-specific reboot buttons
    for node in coordinator.data.get("nodes", []):
        mac = node.get("mac")
        if not mac:
            continue

        buttons.append(
            TendaMeshRebootButton(
                coordinator,
                mac=mac,
                description=ButtonEntityDescription(
                    key="reboot_node",
                    name="Reboot Node",
                    icon="mdi:restart",
                ),
                is_global=False,
            )
        )

    async_add_entities(buttons)


class TendaMeshRebootButton(CoordinatorEntity[TendaMeshCoordinator], ButtonEntity):
    """Representation of a Tenda Mesh reboot button."""

    def __init__(
        self,
        coordinator: TendaMeshCoordinator,
        mac: str,
        description: ButtonEntityDescription,
        is_global: bool,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._mac = mac
        self._is_global = is_global

        entry_id = "unknown"
        if coordinator.config_entry:
            entry_id = coordinator.config_entry.entry_id

        self._attr_unique_id = f"{entry_id}_{mac}_{description.key}"

    @property
    def _get_node(self) -> dict[str, Any] | None:
        """Get the node data from the coordinator."""
        if self._is_global:
            return None
        nodes = cast(list[dict[str, Any]], self.coordinator.data.get("nodes", []))
        for node in nodes:
            if node.get("mac") == self._mac:
                return node
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        entry_id = "unknown"
        if self.coordinator.config_entry:
            entry_id = self.coordinator.config_entry.entry_id

        if self._is_global:
            # Bind to the primary router device
            model = "Tenda Mesh Router"
            sw_version = None
            nodes = self.coordinator.data.get("nodes", [])
            master_node = next((n for n in nodes if n.get("role") == "master"), None)
            if master_node:
                model = str(master_node.get("devModel", model))
                sw_version = str(master_node.get("softVersion", ""))

            return DeviceInfo(
                identifiers={(DOMAIN, entry_id)},
                name=f"Tenda Mesh ({self.coordinator.client.host})",
                manufacturer="Tenda",
                model=model,
                sw_version=sw_version,
                configuration_url=f"http://{self.coordinator.client.host}",
            )

        # Bind to a specific node device
        node = self._get_node
        name = "Unknown Node"
        model = "Tenda Mesh Node"
        sw_version = None
        if node:
            name = str(node.get("name", name))
            model = str(node.get("devModel", model))
            sw_version = str(node.get("softVersion", ""))

        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            name=name,
            manufacturer="Tenda",
            model=model,
            sw_version=sw_version,
            via_device=(DOMAIN, self.coordinator.client.host),
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.coordinator.client.ensure_authenticated()
            try:
                if self._is_global:
                    _LOGGER.info("Rebooting entire Tenda Mesh network")
                    # Module name 'systemReboot' confirmed by user trace
                    payload: dict[str, Any] = {"systemReboot": {}}
                    await self.coordinator.client.set_modules(["systemReboot"], payload)
                else:
                    node = self._get_node
                    if not node:
                        _LOGGER.error(
                            "Cannot reboot node: Node %s not found in mesh topology",
                            self._mac,
                        )
                        return

                    _LOGGER.info(
                        "Rebooting Tenda Mesh node %s", node.get("name", self._mac)
                    )
                    # Node-specific reboot also uses systemReboot module
                    payload = {
                        "systemReboot": {
                            "sn": node.get("sn", ""),
                            "mac": node.get("mac_addr", ""),
                            "ip": node.get("ip", ""),
                        }
                    }
                    await self.coordinator.client.set_modules(["systemReboot"], payload)

                _LOGGER.info("Reboot command sent successfully")
            except TendaConnectionError as err:
                # If we get a "Server disconnected" error during reboot, it's likely
                # because the router started rebooting immediately.
                if "Server disconnected" in str(err):
                    _LOGGER.info("Reboot command sent, connection closed as expected")
                else:
                    raise
        except Exception as err:
            _LOGGER.error("Failed to send reboot command: %s", err)
