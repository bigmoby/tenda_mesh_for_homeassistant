"""Device tracker platform for Tenda Mesh."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COORDINATOR, DOMAIN
from .coordinator import TendaMeshCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device tracker for Tenda Mesh component."""
    coordinator: TendaMeshCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    tracked: dict[str, TendaTracker] = {}

    @callback
    def coordinator_updated() -> None:
        """Update the status of the devices."""
        update_items(coordinator, async_add_entities, tracked)

    entry.async_on_unload(coordinator.async_add_listener(coordinator_updated))

    # Initial update
    coordinator_updated()


@callback
def update_items(
    coordinator: TendaMeshCoordinator,
    async_add_entities: AddEntitiesCallback,
    tracked: dict[str, TendaTracker],
) -> None:
    """Update tracked device state from the hub."""
    new_tracked: list[TendaTracker] = []

    devices = coordinator.data.get("devices", {})

    for mac in devices:
        if mac not in tracked:
            tracker = TendaTracker(coordinator, mac)
            tracked[mac] = tracker
            new_tracked.append(tracker)

    if new_tracked:
        async_add_entities(new_tracked)


class TendaTracker(CoordinatorEntity[TendaMeshCoordinator], ScannerEntity):
    """Representation of a network device."""

    def __init__(
        self,
        coordinator: TendaMeshCoordinator,
        mac: str,
    ) -> None:
        """Initialize the tracked device."""
        super().__init__(coordinator)
        self._mac = mac

    @property
    def _device_data(self) -> dict[str, Any] | None:
        """Get the device data from the coordinator."""
        devices = cast(
            dict[str, dict[str, Any]], self.coordinator.data.get("devices", {})
        )
        return devices.get(self._mac)

    @property
    def is_connected(self) -> bool:
        """Return true if the client is connected to the network."""
        data = self._device_data
        if not data:
            return False
        return bool(data.get("online", False))

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the client."""
        return SourceType.ROUTER

    @property
    def name(self) -> str:
        """Return the name of the client."""
        data = self._device_data
        if not data:
            return self._mac
        return str(data.get("name") or self._mac)

    @property
    def hostname(self) -> str | None:
        """Return the hostname of the client."""
        data = self._device_data
        return str(data["name"]) if data and data.get("name") else None

    @property
    def mac_address(self) -> str:
        """Return the mac address of the client."""
        return self._mac

    @property
    def ip_address(self) -> str | None:
        """Return the ip address of the client."""
        data = self._device_data
        return str(data["ip"]) if data and data.get("ip") else None

    @property
    def unique_id(self) -> str:
        """Return an unique identifier for this device."""
        entry_id = "unknown"
        if self.coordinator.config_entry:
            entry_id = self.coordinator.config_entry.entry_id
        return f"{entry_id}_tracker_{self._mac}"

    @property
    def icon(self) -> str:
        """Return device icon."""
        return "mdi:lan-connect" if self.is_connected else "mdi:lan-disconnect"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        data = self._device_data
        if not data:
            return {}

        attrs: dict[str, Any] = {
            "connection_type": data.get("connection", "unknown"),
        }

        if "uptime" in data:
            attrs["uptime_seconds"] = data["uptime"]

        return attrs
