"""Constants for the Govee light local integration."""

from datetime import timedelta

DOMAIN = "govee_light_local"
MANUFACTURER = "Govee"

CONF_MULTICAST_ADDRESS_DEFAULT = "239.255.255.250"
CONF_TARGET_PORT_DEFAULT = 4001
CONF_LISTENING_PORT_DEFAULT = 4002
CONF_DISCOVERY_INTERVAL_DEFAULT = 60

SCAN_INTERVAL = timedelta(seconds=30)
DISCOVERY_TIMEOUT = 5

CONF_OPTION_DEVICE = "device"

CONF_OPTION_CURRENT_GROUP = "current_group"
CONF_OPTION_GROUP_COUNT = "group_count"
CONF_OPTION_GROUPS = "groups"

CONF_OPTION_SEGMENTS = "segments"
CONF_OPTION_AVAILABLE_SEGMENTS = "available_segments"
CONF_OPTION_SEGMENTS_COUNT = "segments_count"

CONF_OPTION_IMPORT_STRIP = "import_strip"
