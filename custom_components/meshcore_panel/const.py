"""Constants for MeshCore Panel."""

DOMAIN = "meshcore_panel"
PLATFORMS = ["sensor"]

# Default configuration
DEFAULT_ADVERT_THRESHOLD_HOURS = 12
DEFAULT_MESSAGE_THRESHOLD_HOURS = 24
DEFAULT_HEATMAP_THRESHOLD_HOURS = 168
DEFAULT_CLEANUP_DAYS = 30
DEFAULT_MAX_GREET_HOPS = 5
DEFAULT_GREET_CHANNEL = 0

# Persistence files
PERSISTENCE_DIR = "www"
HEATMAP_DATA_FILE = "meshcore_heatmap_data.json"
NODEMAP_DATA_FILE = "meshcore_nodemap_data.json"
DIRECTLINKS_DATA_FILE = "meshcore_directlinks_data.json"
DIRECTLINKS_PERSIST_FILE = "meshcore_directlinks_persist.json"
HOPS_SENSORS_FILE = "meshcore_hops_sensors.json"
LAST_MESSAGES_FILE = "meshcore_last_messages.json"
HOPS_DATA_FILE = "meshcore_hops_data.json"
GREETED_FILE = "meshcore_greeted.json"

# Configuration keys
CONF_MY_REPEATER_PUBKEY = "my_repeater_pubkey"
CONF_MY_NAME = "my_name"
CONF_GREET_ENABLED = "greet_enabled"
CONF_CLEANUP_ENABLED = "cleanup_enabled"
