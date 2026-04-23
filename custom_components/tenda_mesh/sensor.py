"""Sensor platform for Tenda Mesh integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COORDINATOR, DOMAIN, MANUFACTURER
from .coordinator import TendaMeshCoordinator

# ---------------------------------------------------------------------------
# Global (router-wide) sensors
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class TendaGlobalSensorDescription(SensorEntityDescription):
    """Class describing Tenda global sensor entities."""

    value_fn: Callable[[dict[str, Any]], Any] = lambda d: None


GLOBAL_SENSOR_DESCRIPTIONS: tuple[TendaGlobalSensorDescription, ...] = (
    TendaGlobalSensorDescription(
        key="wan_status",
        name="WAN Status",
        icon="mdi:wan",
        value_fn=lambda d: d.get("wan", {}).get("status"),
    ),
    TendaGlobalSensorDescription(
        key="wan_ip",
        name="WAN IP Address",
        icon="mdi:ip-network",
        value_fn=lambda d: d.get("wan", {}).get("ip") or None,
    ),
    TendaGlobalSensorDescription(
        key="total_clients",
        name="Total Connected Clients",
        icon="mdi:devices",
        native_unit_of_measurement="clients",
        value_fn=lambda d: d.get("total_clients"),
    ),
    TendaGlobalSensorDescription(
        key="ssid_24g",
        name="SSID 2.4 GHz",
        icon="mdi:wifi",
        value_fn=lambda d: d.get("ssids", {}).get("2.4G"),
    ),
    TendaGlobalSensorDescription(
        key="ssid_5g",
        name="SSID 5 GHz",
        icon="mdi:wifi",
        value_fn=lambda d: d.get("ssids", {}).get("5G"),
    ),
    TendaGlobalSensorDescription(
        key="ssid_6g",
        name="SSID 6 GHz",
        icon="mdi:wifi",
        value_fn=lambda d: d.get("ssids", {}).get("6G"),
    ),
)


# ---------------------------------------------------------------------------
# Per-node sensors
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class TendaNodeSensorDescription(SensorEntityDescription):
    """Class describing Tenda node sensor entities."""

    value_fn: Callable[[dict[str, Any]], Any] = lambda n: None
    extra_attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


NODE_SENSOR_DESCRIPTIONS: tuple[TendaNodeSensorDescription, ...] = (
    TendaNodeSensorDescription(
        key="clients",
        name="Connected Clients",
        icon="mdi:laptop",
        native_unit_of_measurement="clients",
        value_fn=lambda n: n.get("clients"),
    ),
    TendaNodeSensorDescription(
        key="hop",
        name="Mesh Hop Count",
        icon="mdi:graph",
        native_unit_of_measurement="hops",
        value_fn=lambda n: n.get("hop"),
    ),
    TendaNodeSensorDescription(
        key="role",
        name="Node Role",
        icon="mdi:router-network",
        value_fn=lambda n: n.get("role"),
    ),
    TendaNodeSensorDescription(
        key="ip",
        name="IP Address",
        icon="mdi:ip",
        value_fn=lambda n: n.get("ip") or None,
    ),
    TendaNodeSensorDescription(
        key="connect_status",
        name="Connection Status",
        icon="mdi:wifi-star",
        value_fn=lambda n: str(n.get("connect_status", "unknown")).title(),
        extra_attributes_fn=lambda n: {
            "connection_type": n.get("connect_type", "unknown")
        },
    ),
    TendaNodeSensorDescription(
        key="uptime",
        name="Uptime",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda n: n.get("uptime"),
    ),
)


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tenda Mesh sensors from config entry."""
    coordinator: TendaMeshCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    # Global sensors (one device: the hub)
    entities: list[SensorEntity] = [
        TendaGlobalSensor(coordinator, entry, desc)
        for desc in GLOBAL_SENSOR_DESCRIPTIONS
    ]

    # Per-node sensors (one device per mesh node)
    entities.extend(
        TendaNodeSensor(coordinator, entry, desc, node["mac"])
        for node in coordinator.data.get("nodes", [])
        for desc in NODE_SENSOR_DESCRIPTIONS
    )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Entity classes
# ---------------------------------------------------------------------------


class TendaGlobalSensor(CoordinatorEntity[TendaMeshCoordinator], SensorEntity):
    """A sensor representing a router-wide metric."""

    _attr_has_entity_name = True
    entity_description: TendaGlobalSensorDescription

    def __init__(
        self,
        coordinator: TendaMeshCoordinator,
        entry: ConfigEntry,
        description: TendaGlobalSensorDescription,
    ) -> None:
        """Initialize the global sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Tenda Mesh ({entry.data['host']})",
            manufacturer=MANUFACTURER,
            model="Mesh Router",
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class TendaNodeSensor(CoordinatorEntity[TendaMeshCoordinator], SensorEntity):
    """A sensor representing a per-node metric."""

    _attr_has_entity_name = True
    entity_description: TendaNodeSensorDescription

    def __init__(
        self,
        coordinator: TendaMeshCoordinator,
        entry: ConfigEntry,
        description: TendaNodeSensorDescription,
        mac: str,
    ) -> None:
        """Initialize the node sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._mac = mac
        self._attr_unique_id = f"{entry.entry_id}_node_{mac}_{description.key}"
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
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        node = self._get_node()
        if node is None:
            return None
        return self.entity_description.value_fn(node)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        node = self._get_node()
        if node is None:
            return None

        attrs: dict[str, Any] = {}
        # Expose the connected devices list only on the "clients" sensor
        if self.entity_description.key == "clients":
            attrs["connected_devices"] = node.get("client_list", [])

        if self.entity_description.extra_attributes_fn:
            attrs.update(self.entity_description.extra_attributes_fn(node))

        return attrs if attrs else None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._get_node() is not None
