"""Constants for the Tenda Mesh integration."""

DOMAIN = "tenda_mesh"
MANUFACTURER = "Tenda"

# Config entry keys
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Defaults
DEFAULT_USERNAME = "admin"
DEFAULT_SCAN_INTERVAL = 60  # seconds
DEFAULT_SCHEME = "http"
DEFAULT_PORT = 80

# HTTP
HTTP_TIMEOUT = 10  # seconds
AES_IV = b"EU5H62G9ICGRNI43"
UDP_PORT = 9801

# HA coordinator
COORDINATOR = "coordinator"

# Modules to poll via getModules
MODULES_DASHBOARD = [
    "meshTopo",
    "wanStatus",
    "deviceListNotNeedRate",
    "wifiBasicCfg",
    "ledCfg",
    "apModeStatus",
    "workMode",
]

# Band labels (as returned by the router firmware)
BAND_LABELS: dict[int, str] = {
    2: "2.4G",
    4: "5G",
    6: "6G",
}
