# Tenda Mesh – Home Assistant Custom Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

[![GitHub Release][releases-shield]][releases]
![Project Stage][project-stage-shield]
[![License][license-shield]](LICENSE.md)

![Maintenance][maintenance-shield]
[![GitHub Activity][commits-shield]][commits]

[![Donate](https://img.shields.io/badge/donate-BuyMeCoffee-yellow.svg)](https://www.buymeacoffee.com/bigmoby)

Local integration for **Tenda Mesh** routers (EX3, EX6, MX3, MX6 and compatible variants).

It communicates directly with the router via local HTTP — no cloud, no Tenda account required.

---

## Features

| Entity         | Type            | Description                                      |
| -------------- | --------------- | ------------------------------------------------ |
| WAN Status     | `sensor`        | WAN connection status (connected / disconnected) |
| WAN IP         | `sensor`        | Public WAN IP address                            |
| Total Clients  | `sensor`        | Total number of devices connected to the mesh    |
| SSID 2.4 GHz   | `sensor`        | 2.4 GHz Wi-Fi network name                       |
| SSID 5 GHz     | `sensor`        | 5 GHz Wi-Fi network name                         |
| SSID 6 GHz     | `sensor`        | 6 GHz Wi-Fi network name (if supported)          |
| Node Online    | `binary_sensor` | Mesh node reachable (connectivity)               |
| Node Clients   | `sensor`        | Clients connected to the single node             |
| Node Link Rate | `sensor`        | Link rate to the master (Mbps)                   |
| Node Hop Count | `sensor`        | Number of hops from the root                     |
| Node Role      | `sensor`        | `master` or `satellite`                          |
| Node IP        | `sensor`        | Node IP address                                  |

---

## Installation

### Manual

1. Copy the `custom_components/tenda_mesh/` folder into the `config/custom_components/` directory of your Home Assistant installation.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → + Add Integration**.
4. Search for **Tenda Mesh** and follow the setup wizard.

### HACS

1. In HACS, add this repository as a **Custom Repository** (category: _Integration_).
2. Install **Tenda Mesh**.
3. Restart Home Assistant.
4. Configure the integration as described above.

---

## Configuration

During the setup wizard, the following are required:

| Field          | Description                         | Default |
| -------------- | ----------------------------------- | ------- |
| **IP Address** | Local IP of the Tenda master router | —       |
| **Username**   | Local panel user                    | `admin` |
| **Password**   | Local panel password (plain text)   | —       |

The password is hashed with MD5-uppercase before being sent to the router (native Tenda scheme) and **is never transmitted in plain text to the API**.

---

## Requirements

- Home Assistant **2026.1.0** or higher
- Python library: `pycryptodome>=3.19.0` (automatically installed by HA)
- The Tenda router must be reachable on the same local network

---

## Architecture

```
config_flow  ──▶  ConfigEntry
                     │
                     ▼
            TendaMeshCoordinator  (polling every N sec)
                     │
                     ▼
            TendaLocalClient (aiohttp, AES encrypt/decrypt)
                     │
                     ▼
            Tenda Mesh Router (local HTTP)
```

The integration reuses the session token (`stok`) and encryption key (`sign`). A full login sequence is performed only on startup or when the session expires:

1. `GET /goform/loginInfo` (pre-login)
2. `POST /login/Auth` (authentication)
3. `GET /goform/stokCfg` (stok + sign retrieval)

Standard updates then only call:
4. `GET /;stok=.../goform/getModules` with modules: `meshTopo`, `wanStatus`, `deviceListNotNeedRate`, `wifiBasicCfg`, `ledCfg`, `apModeStatus`, `workMode`

---

## Lovelace Dashboard (Connected Devices)

Individual devices connected to a node (phones, PCs, etc.) are not created as separate `device_tracker` entities to avoid flooding Home Assistant with unnecessary entities. Instead, the full list of devices is exposed as an **attribute** of the `Connected Clients` sensor.

To easily view the table of connected devices on your Lovelace dashboard, you can use the built-in Home Assistant **Markdown Card**.

### Example Markdown Card Configuration

Add a new manual card to your dashboard and paste this code (make sure to replace `sensor.tenda_node_xxxxxx_connected_clients` with the actual ID of your sensor, which you can find in the integration's entity list):

```yaml
type: markdown
content: |
  ### Devices on {{ state_attr('sensor.tenda_node_xxxxxx_connected_clients', 'friendly_name') | replace(' Connected Clients', '') }}
  | Device Name | IP Address | MAC Address | Connection Type |
  | :--- | :--- | :--- | :--- |
  {% for device in state_attr('sensor.tenda_node_xxxxxx_connected_clients', 'connected_devices') -%}
  | {{ device.name }} | {{ device.ip }} | {{ device.mac }} | {{ device.connection }} |
  {% endfor %}
```

This will generate a dynamic table that automatically updates showing the name, IP, MAC, and type (e.g., `2.4G`, `5G`, `wire`) of each device connected to that specific node.

---

## Contributing

This is an active open-source project. We are always open to people who want to
use the code or contribute to it.

We have set up a separate document containing our
[contribution guidelines](CONTRIBUTING.md).

Thank you for being involved! :heart_eyes:

## Sponsor

Please, if You want support this kind of projects:

<a href="https://www.buymeacoffee.com/bigmoby" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

Many Thanks,

Fabio Mauro

## Authors & contributors

Fabio Mauro Bigmoby

[releases-shield]: https://img.shields.io/github/release/bigmoby/tenda_mesh_for_homeassistant.svg
[releases]: https://github.com/bigmoby/tenda_mesh_for_homeassistant/releases
[project-stage-shield]: https://img.shields.io/badge/project%20stage-production%20ready-brightgreen.svg
[license-shield]: https://img.shields.io/github/license/bigmoby/tenda_mesh_for_homeassistant
[maintenance-shield]: https://img.shields.io/maintenance/yes/2026.svg
[commits-shield]: https://img.shields.io/github/commit-activity/y/bigmoby/tenda_mesh_for_homeassistant.svg
[commits]: https://img.shields.io/github/commits/bigmoby/tenda_mesh_for_homeassistant
