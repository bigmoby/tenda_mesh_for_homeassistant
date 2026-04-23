"""DataUpdateCoordinator for Tenda Mesh."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.dt import utc_from_timestamp

from .api import TendaAuthError, TendaConnectionError, TendaLocalClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, MODULES_DASHBOARD

_LOGGER = logging.getLogger(__name__)


class TendaMeshCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls the Tenda router and parses mesh data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: TendaLocalClient,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )
        self.client = client

    # ------------------------------------------------------------------
    # Core update
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            await self.client.ensure_authenticated()
            raw = await self.client.get_modules(MODULES_DASHBOARD)
        except TendaAuthError:
            _LOGGER.debug("Session expired or invalid, attempting re-authentication")
            try:
                self.client.stok = None
                self.client.sign = None
                await self.client.ensure_authenticated()
                raw = await self.client.get_modules(MODULES_DASHBOARD)
            except TendaAuthError as exc:
                raise ConfigEntryAuthFailed("Re-authentication failed") from exc
            except Exception as exc:
                raise UpdateFailed(f"Unexpected error during re-auth: {exc}") from exc
        except TendaConnectionError as exc:
            raise UpdateFailed(str(exc)) from exc
        except Exception as exc:
            raise UpdateFailed(f"Unexpected error: {exc}") from exc

        return self._parse(raw)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse(self, raw: Any) -> dict[str, Any]:
        """Normalise the getModules response into a structured dict."""
        if not isinstance(raw, dict):
            _LOGGER.warning("Unexpected getModules response type: %s", type(raw))
            return {}

        result: dict[str, Any] = {
            "wan": {},
            "ssids": {},
            "total_clients": 0,
            "nodes": [],
        }

        # -- WAN status ------------------------------------------------
        wan = raw.get("wanStatus") or {}
        result["wan"] = {
            "status": wan.get("connectStatus", "unknown"),
            "ip": wan.get("wanIP", ""),
            "type": wan.get("wanType", ""),
        }

        device_lists = raw.get("deviceList") or raw.get("deviceListNotNeedRate") or []
        total_clients = 0
        node_enrichment: dict[str, dict[str, str]] = {}
        node_clients: dict[str, list[dict[str, Any]]] = {}
        all_devices: dict[str, dict[str, Any]] = {}

        def _parse_client(client: dict[str, Any], is_online: bool) -> None:
            mac = client.get("mac")
            if not mac:
                return

            name = (
                client.get("hostname")
                or client.get("devName")
                or client.get("deviceName")
                or client.get("manufacturer")
                or mac
                or "Unknown Device"
            )
            ip = client.get("ip", "")
            connection = client.get("connectType", "unknown")

            all_devices[mac] = {
                "mac": mac,
                "name": name,
                "ip": ip,
                "connection": connection,
                "uptime": int(client.get("connectTime") or 0),
                "online": is_online,
            }

            # Map to node only if online
            if is_online:
                access_node = client.get("accessNode", {})
                sn = access_node.get("sn")
                if sn:
                    if sn not in node_enrichment:
                        node_enrichment[sn] = {
                            "ip": access_node.get("ip", ""),
                            "mac_addr": access_node.get("mac", ""),
                        }
                    if sn not in node_clients:
                        node_clients[sn] = []
                    node_clients[sn].append(
                        {
                            "name": name,
                            "ip": ip,
                            "mac": mac,
                            "connection": connection,
                            "uptime": int(client.get("connectTime") or 0),
                        }
                    )

        if isinstance(device_lists, list):
            for dev_list in device_lists:
                online_list = dev_list.get("onlineList") or []
                offline_list = dev_list.get("offlineList") or []
                guest_list = dev_list.get("guestList") or []

                total_clients += len(online_list) + len(guest_list)

                for client in online_list:
                    _parse_client(client, True)
                for client in guest_list:
                    _parse_client(client, True)
                for client in offline_list:
                    _parse_client(client, False)

        result["total_clients"] = total_clients
        result["devices"] = all_devices

        # -- Mesh topology (nodes) -------------------------------------
        def flatten_topo(
            node: dict[str, Any], current_hop: int = 0
        ) -> list[dict[str, Any]]:
            if not node:
                return []
            nodes = []
            if "sn" in node or "mac" in node:
                # Add calculated hop into the node dictionary
                node["calculated_hop"] = current_hop
                nodes.append(node)
            for child in node.get("childNode", []):
                nodes.extend(flatten_topo(child, current_hop + 1))
            return nodes

        topo = raw.get("meshTopo") or {}
        if isinstance(topo, list) and len(topo) > 0:
            topo = topo[0]
        result["nodes"] = flatten_topo(topo)

        for n in result["nodes"]:
            # Normalization so sensor/binary_sensor logic works
            sn = n.get("sn")
            enrich = node_enrichment.get(sn) or {}
            n["mac"] = sn or "unknown_sn"  # Static unique identifier
            n["mac_addr"] = enrich.get("mac_addr") or ""
            n["ip"] = enrich.get("ip") or n.get("ip") or ""
            n["name"] = n.get("nodeName") or sn or "Unknown Node"
            n["online"] = n.get("connectStatus") != "Disconnected"
            n["role"] = "master" if n.get("nodeType") == "controller" else "satellite"
            n["connect_status"] = n.get("connectStatus", "unknown")
            n["connect_type"] = n.get("connectType", "unknown")
            # Calculate boot time for better UI display (timestamp class)
            uptime_seconds = int(n.get("connectTime") or 0)
            if uptime_seconds > 0:
                n["uptime"] = utc_from_timestamp(time.time() - uptime_seconds)
            else:
                n["uptime"] = None
            # Number of clients connected to this specific node
            n["clients"] = int(n.get("clientNum") or 0)
            n["client_list"] = node_clients.get(sn, [])
            n["hop"] = n.get("calculated_hop", 0)

        # -- Wi-Fi SSIDs -----------------------------------------------
        wifi = raw.get("wifiBasicCfg") or {}
        if isinstance(wifi, dict):
            if wifi.get("wifiEn"):
                result["ssids"]["2.4G"] = wifi.get("wifiSSID", "")
            if wifi.get("wifiEn_5g"):
                result["ssids"]["5G"] = wifi.get("wifiSSID_5g", "")
            if wifi.get("wifiEn_6g"):
                result["ssids"]["6G"] = wifi.get("wifiSSID_6g", "")

        return result
