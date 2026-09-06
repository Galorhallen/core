"""Constants for the Govee light local integration."""

from datetime import timedelta

DOMAIN = "govee_light_local"
MANUFACTURER = "Govee"

CONF_MULTICAST_ADDRESS_DEFAULT = "239.255.255.250"
CONF_TARGET_PORT_DEFAULT = 4001
CONF_LISTENING_PORT_DEFAULT = 4002
CONF_DISCOVERY_INTERVAL_DEFAULT = 60

SCAN_INTERVAL = timedelta(seconds=30)
# A device is considered unavailable if we have not heard a status response
# from it for three consecutive poll cycles. This tolerates a single dropped
# UDP response plus some jitter before flapping the entity state.
DEVICE_TIMEOUT = SCAN_INTERVAL * 3
DISCOVERY_TIMEOUT = 5

CONF_AUTO_DISCOVERY = "auto_discovery"
CONF_MANUAL_DEVICES = "manual_devices"
CONF_DEVICE_IP = "device_ip"
# Field key of the removal form only; the removal is expressed by the IP
# disappearing from CONF_MANUAL_DEVICES, not by a persisted work list.
CONF_IPS_TO_REMOVE = "ips_to_remove"
