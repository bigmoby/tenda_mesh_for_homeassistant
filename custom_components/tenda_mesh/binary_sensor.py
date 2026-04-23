"""Binary sensor platform for Tenda Mesh integration (node online/offline)."""

from __future__ import annotations

from typing import Any, cast

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COORDINATOR, DOMAIN, MANUFACTURER
from .coordinator import TendaMeshCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tenda Mesh binary sensors from config entry."""
    coordinator: TendaMeshCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    entities = [
        TendaNodeOnlineSensor(coordinator, entry, node["mac"])
        for node in coordinator.data.get("nodes", [])
    ]
    async_add_entities(entities)


class TendaNodeOnlineSensor(
    CoordinatorEntity[TendaMeshCoordinator], BinarySensorEntity
):
    """Binary sensor: True when a mesh node is reachable (present in topoList)."""

    _attr_has_entity_name = True
    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: TendaMeshCoordinator,
        entry: ConfigEntry,
        mac: str,
    ) -> None:
        """Initialize the node online binary sensor."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{entry.entry_id}_node_{mac}_online"
        self._entry_id = entry.entry_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this node."""
        node = self._get_node()
        name = node.get("name") if node else f"Tenda Node {self._mac[-6:]}"
        return DeviceInfo(
            identifiers={(DOMAIN, self._mac)},
            name=name,
            manufacturer=MANUFACTURER,
            model="Mesh Node",
            via_device=(DOMAIN, self._entry_id),
        )

    def _get_node(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        for node in self.coordinator.data.get("nodes", []):
            if isinstance(node, dict) and node.get("mac") == self._mac:
                return cast(dict[str, Any], node)
        return None

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        node = self._get_node()
        if node is None:
            return None
        return bool(node.get("online", False))

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success
