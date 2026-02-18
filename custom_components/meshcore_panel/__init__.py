"""MeshCore Panel Integration for Home Assistant."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    PLATFORMS,
    PERSISTENCE_DIR,
    HEATMAP_DATA_FILE,
    NODEMAP_DATA_FILE,
    DIRECTLINKS_DATA_FILE,
    DIRECTLINKS_PERSIST_FILE,
    HOPS_SENSORS_FILE,
    LAST_MESSAGES_FILE,
    GREETED_FILE,
    CONF_MY_REPEATER_PUBKEY,
    CONF_MY_NAME,
    CONF_GREET_ENABLED,
    CONF_CLEANUP_ENABLED,
    DEFAULT_CLEANUP_DAYS,
    DEFAULT_MAX_GREET_HOPS,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS_LIST = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MeshCore Panel from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    coordinator = MeshCorePanelCoordinator(hass, entry)
    await coordinator.async_initialize()
    
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS_LIST)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS_LIST)
    
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    
    return unload_ok


class MeshCorePanelCoordinator:
    """Coordinator for MeshCore Panel."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self._unsub_listeners = []
        
        # Configuration
        self.my_repeater_pubkey = entry.data.get(CONF_MY_REPEATER_PUBKEY, "")
        self.my_name = entry.data.get(CONF_MY_NAME, "MyRepeater")
        self.greet_enabled = entry.data.get(CONF_GREET_ENABLED, True)
        self.cleanup_enabled = entry.data.get(CONF_CLEANUP_ENABLED, True)
        
        # Data caches
        self.direct_links = {}
        self.last_message_times = {}
        self.hops_sensors_data = {}
        self.greeted_pubkeys = set()
        self.hop_nodes_used = {}
        
        # Paths
        self.www_path = hass.config.path(PERSISTENCE_DIR)

    async def async_initialize(self) -> None:
        """Initialize the coordinator."""
        # Load persisted data
        await self.hass.async_add_executor_job(self._load_persisted_data)
        
        # Listen for MeshCore events
        self._unsub_listeners.append(
            self.hass.bus.async_listen("meshcore_raw_event", self._handle_meshcore_event)
        )
        
        # Schedule periodic tasks
        self._unsub_listeners.append(
            async_track_time_interval(
                self.hass,
                self._async_export_data,
                timedelta(minutes=5),
            )
        )
        
        # Schedule daily cleanup at 3am
        if self.cleanup_enabled:
            self._unsub_listeners.append(
                async_track_time_interval(
                    self.hass,
                    self._async_cleanup_old_contacts,
                    timedelta(hours=24),
                )
            )
        
        # Initial export
        await self._async_export_data(None)
        
        _LOGGER.info("MeshCore Panel initialized")

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        for unsub in self._unsub_listeners:
            unsub()
        
        # Save data before shutdown
        await self.hass.async_add_executor_job(self._save_persisted_data)

    def _load_persisted_data(self) -> None:
        """Load persisted data from files."""
        # Load direct links
        path = os.path.join(self.www_path, DIRECTLINKS_PERSIST_FILE)
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    self.direct_links = data.get("direct_links", {})
            except Exception as e:
                _LOGGER.warning(f"Error loading direct links: {e}")
        
        # Load last message times
        path = os.path.join(self.www_path, LAST_MESSAGES_FILE)
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    self.last_message_times = data.get("last_messages", {})
            except Exception as e:
                _LOGGER.warning(f"Error loading last messages: {e}")
        
        # Load hops sensors
        path = os.path.join(self.www_path, HOPS_SENSORS_FILE)
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    self.hops_sensors_data = data.get("sensors", {})
            except Exception as e:
                _LOGGER.warning(f"Error loading hops sensors: {e}")
        
        # Load greeted contacts
        path = os.path.join(self.www_path, GREETED_FILE)
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    self.greeted_pubkeys = set(data.get("greeted", []))
            except Exception as e:
                _LOGGER.warning(f"Error loading greeted list: {e}")

    def _save_persisted_data(self) -> None:
        """Save persisted data to files."""
        now_ts = time.time()
        max_age = 7 * 24 * 3600  # 7 days
        
        # Clean and save direct links
        cleaned_links = {}
        for node_a, connections in self.direct_links.items():
            cleaned_connections = {}
            for node_b, link_data in connections.items():
                if (now_ts - link_data.get("last_seen", 0)) <= max_age:
                    cleaned_connections[node_b] = link_data
            if cleaned_connections:
                cleaned_links[node_a] = cleaned_connections
        self.direct_links = cleaned_links
        
        path = os.path.join(self.www_path, DIRECTLINKS_PERSIST_FILE)
        try:
            with open(path, 'w') as f:
                json.dump({
                    "direct_links": self.direct_links,
                    "saved_at": now_ts,
                }, f, indent=2)
        except Exception as e:
            _LOGGER.error(f"Error saving direct links: {e}")
        
        # Clean and save last messages
        cleaned_messages = {k: v for k, v in self.last_message_times.items() 
                          if (now_ts - v) <= max_age}
        self.last_message_times = cleaned_messages
        
        path = os.path.join(self.www_path, LAST_MESSAGES_FILE)
        try:
            with open(path, 'w') as f:
                json.dump({
                    "last_messages": self.last_message_times,
                    "saved_at": now_ts,
                }, f, indent=2)
        except Exception as e:
            _LOGGER.error(f"Error saving last messages: {e}")
        
        # Save greeted contacts
        path = os.path.join(self.www_path, GREETED_FILE)
        try:
            with open(path, 'w') as f:
                json.dump({
                    "greeted": list(self.greeted_pubkeys),
                    "count": len(self.greeted_pubkeys),
                }, f, indent=2)
        except Exception as e:
            _LOGGER.error(f"Error saving greeted list: {e}")

    @callback
    def _handle_meshcore_event(self, event) -> None:
        """Handle MeshCore raw events."""
        event_type = event.data.get("event_type", "")
        payload = event.data.get("payload", {})
        
        if event_type == "EventType.RX_LOG_DATA":
            self._process_rx_log_data(payload)
        elif event_type == "EventType.NEW_CONTACT":
            self._process_new_contact(payload)

    def _process_rx_log_data(self, payload: dict) -> None:
        """Process RX_LOG_DATA events for path tracking."""
        parsed = payload.get("parsed", {})
        path_nodes = parsed.get("path_nodes", [])
        
        if len(path_nodes) < 2:
            return
        
        now_ts = time.time()
        
        # Record direct links between consecutive nodes
        for i in range(len(path_nodes) - 1):
            node_a = path_nodes[i].lower()
            node_b = path_nodes[i + 1].lower()
            
            self._record_direct_link(node_a, node_b, now_ts)
            self._record_direct_link(node_b, node_a, now_ts)

    def _record_direct_link(self, node_a: str, node_b: str, timestamp: float) -> None:
        """Record a direct link between two nodes."""
        if node_a not in self.direct_links:
            self.direct_links[node_a] = {}
        
        if node_b in self.direct_links[node_a]:
            self.direct_links[node_a][node_b]["last_seen"] = timestamp
            self.direct_links[node_a][node_b]["count"] = \
                self.direct_links[node_a][node_b].get("count", 0) + 1
        else:
            self.direct_links[node_a][node_b] = {
                "last_seen": timestamp,
                "count": 1
            }

    def _process_new_contact(self, payload: dict) -> None:
        """Process new contact events for greeting."""
        if not self.greet_enabled:
            return
        
        pubkey = payload.get("public_key", "")[:12]
        name = payload.get("adv_name", "Unknown")
        node_type = payload.get("type", 0)
        
        # Only greet clients, not repeaters (type 2) or room servers (type 3)
        if node_type == 2:
            return
        
        if not pubkey or pubkey in self.greeted_pubkeys:
            return
        
        # Send greeting
        self._send_greeting(name, pubkey)

    def _send_greeting(self, name: str, pubkey: str) -> None:
        """Send greeting to new contact."""
        self.greeted_pubkeys.add(pubkey)
        
        message = f"Welcome to the mesh {name}! 👋 from {self.my_name}"
        
        try:
            self.hass.services.call(
                "meshcore",
                "send_channel_message",
                {"channel": 0, "text": message},
            )
            
            # Send HA notification
            self.hass.services.call(
                "persistent_notification",
                "create",
                {
                    "title": "🆕 New MeshCore Contact",
                    "message": f"**{name}**\nPubkey: {pubkey}\n\nGreeted on Public channel",
                },
            )
            
            _LOGGER.info(f"Greeted new contact: {name} ({pubkey})")
        except Exception as e:
            _LOGGER.error(f"Error sending greeting: {e}")
            self.greeted_pubkeys.discard(pubkey)

    async def _async_cleanup_old_contacts(self, now=None) -> None:
        """Cleanup old contacts."""
        await self.hass.async_add_executor_job(self._cleanup_old_contacts)

    def _cleanup_old_contacts(self) -> None:
        """Remove contacts older than threshold."""
        now_ts = time.time()
        threshold_sec = DEFAULT_CLEANUP_DAYS * 24 * 3600
        
        states = self.hass.states.async_all()
        
        for state in states:
            if not (state.entity_id.startswith("binary_sensor.meshcore_") and 
                    "_contact" in state.entity_id):
                continue
            
            attrs = state.attributes
            last_advert = attrs.get("last_advert")
            last_message = self.last_message_times.get(attrs.get("pubkey_prefix"))
            
            # Check if both are old
            advert_old = not last_advert or (now_ts - last_advert) > threshold_sec
            message_old = not last_message or (now_ts - last_message) > threshold_sec
            
            if advert_old and message_old:
                pubkey = attrs.get("pubkey_prefix")
                if pubkey:
                    try:
                        self.hass.services.call(
                            "meshcore",
                            "execute_command",
                            {"command": f"remove_contact {pubkey}"},
                        )
                        _LOGGER.info(f"Removed old contact: {pubkey}")
                    except Exception as e:
                        _LOGGER.warning(f"Error removing contact: {e}")

    async def _async_export_data(self, now=None) -> None:
        """Export data to JSON files for HTML maps."""
        await self.hass.async_add_executor_job(self._export_data)

    def _export_data(self) -> None:
        """Export heatmap, nodemap, and directlinks data."""
        self._export_heatmap_data()
        self._export_nodemap_data()
        self._export_directlinks_data()
        self._save_persisted_data()

    def _get_threshold_hours(self, entity_id: str, default: float) -> float:
        """Get threshold from input_number entity."""
        state = self.hass.states.get(entity_id)
        if state:
            try:
                return float(state.state)
            except ValueError:
                pass
        return default

    def _export_heatmap_data(self) -> None:
        """Export heatmap data to JSON."""
        threshold_hours = self._get_threshold_hours(
            "input_number.meshcore_heatmap_threshold_hours", 168.0
        )
        threshold_sec = threshold_hours * 3600
        now_ts = time.time()
        
        # Collect hop node data
        node_data = {}
        states = self.hass.states.async_all()
        
        for state in states:
            if "meshcore_hops_" not in state.entity_id:
                continue
            
            attrs = state.attributes
            last_msg = attrs.get("last_message_time")
            if not last_msg or (now_ts - last_msg) > threshold_sec:
                continue
            
            # Process path nodes
            path_nodes = attrs.get("path_nodes", [])
            for node_prefix in path_nodes:
                node_info = self._get_node_info(node_prefix)
                if node_info:
                    key = node_info["pubkey"]
                    if key not in node_data:
                        node_data[key] = {
                            "name": node_info["name"],
                            "lat": node_info["lat"],
                            "lon": node_info["lon"],
                            "use_count": 0,
                        }
                    node_data[key]["use_count"] += 1
        
        # Write to file
        nodes_list = sorted(node_data.values(), key=lambda x: x["use_count"], reverse=True)
        
        path = os.path.join(self.www_path, HEATMAP_DATA_FILE)
        try:
            with open(path, 'w') as f:
                json.dump({
                    "threshold_hours": threshold_hours,
                    "nodes": nodes_list,
                    "paths": [],
                    "updated": now_ts,
                }, f, indent=2)
        except Exception as e:
            _LOGGER.error(f"Error exporting heatmap data: {e}")

    def _export_nodemap_data(self) -> None:
        """Export nodemap data to JSON."""
        threshold_hours = self._get_threshold_hours(
            "input_number.meshcore_advert_threshold_hours", 12.0
        )
        threshold_sec = threshold_hours * 3600
        now_ts = time.time()
        
        nodes_list = []
        states = self.hass.states.async_all()
        
        for state in states:
            if not (state.entity_id.startswith("binary_sensor.meshcore_") and 
                    "_contact" in state.entity_id):
                continue
            
            attrs = state.attributes
            last_advert = attrs.get("last_advert")
            if not last_advert or (now_ts - last_advert) > threshold_sec:
                continue
            
            lat = attrs.get("adv_lat") or attrs.get("latitude")
            lon = attrs.get("adv_lon") or attrs.get("longitude")
            
            if lat and lon:
                nodes_list.append({
                    "name": attrs.get("adv_name", "Unknown"),
                    "lat": float(lat),
                    "lon": float(lon),
                    "node_type": attrs.get("node_type_str", "Unknown").lower(),
                    "age_hours": (now_ts - last_advert) / 3600,
                })
        
        path = os.path.join(self.www_path, NODEMAP_DATA_FILE)
        try:
            with open(path, 'w') as f:
                json.dump({
                    "threshold_hours": threshold_hours,
                    "nodes": nodes_list,
                    "updated": now_ts,
                }, f, indent=2)
        except Exception as e:
            _LOGGER.error(f"Error exporting nodemap data: {e}")

    def _export_directlinks_data(self) -> None:
        """Export direct links data to JSON."""
        threshold_hours = self._get_threshold_hours(
            "input_number.meshcore_heatmap_threshold_hours", 168.0
        )
        threshold_sec = threshold_hours * 3600
        now_ts = time.time()
        
        node_data = {}
        link_data = []
        
        for node_a_prefix, connections in self.direct_links.items():
            node_a_info = self._get_node_info(node_a_prefix)
            if not node_a_info:
                continue
            
            for node_b_prefix, link_info in connections.items():
                if (now_ts - link_info.get("last_seen", 0)) > threshold_sec:
                    continue
                
                node_b_info = self._get_node_info(node_b_prefix)
                if not node_b_info:
                    continue
                
                # Track node
                if node_a_info["pubkey"] not in node_data:
                    node_data[node_a_info["pubkey"]] = {
                        "name": node_a_info["name"],
                        "lat": node_a_info["lat"],
                        "lon": node_a_info["lon"],
                        "node_type": node_a_info.get("node_type", "unknown"),
                        "link_count": 0,
                    }
                node_data[node_a_info["pubkey"]]["link_count"] += 1
                
                # Create link (avoid duplicates)
                link_key = tuple(sorted([node_a_info["pubkey"], node_b_info["pubkey"]]))
                existing = False
                for link in link_data:
                    if tuple(sorted([link["from_pubkey"], link["to_pubkey"]])) == link_key:
                        existing = True
                        link["count"] = max(link["count"], link_info.get("count", 1))
                        break
                
                if not existing:
                    link_data.append({
                        "from_pubkey": node_a_info["pubkey"],
                        "from_name": node_a_info["name"],
                        "from_lat": node_a_info["lat"],
                        "from_lon": node_a_info["lon"],
                        "to_pubkey": node_b_info["pubkey"],
                        "to_name": node_b_info["name"],
                        "to_lat": node_b_info["lat"],
                        "to_lon": node_b_info["lon"],
                        "count": link_info.get("count", 1),
                    })
        
        nodes_list = sorted(node_data.values(), key=lambda x: x["link_count"], reverse=True)
        
        path = os.path.join(self.www_path, DIRECTLINKS_DATA_FILE)
        try:
            with open(path, 'w') as f:
                json.dump({
                    "threshold_hours": threshold_hours,
                    "nodes": nodes_list,
                    "links": link_data,
                    "updated": now_ts,
                }, f, indent=2)
        except Exception as e:
            _LOGGER.error(f"Error exporting directlinks data: {e}")

    def _get_node_info(self, pubkey_prefix: str) -> dict | None:
        """Get node info from contact sensors."""
        matches = []
        states = self.hass.states.async_all()
        
        for state in states:
            if not (state.entity_id.startswith("binary_sensor.meshcore_") and 
                    "_contact" in state.entity_id):
                continue
            
            attrs = state.attributes
            pubkey = attrs.get("pubkey_prefix", "").lower()
            
            if pubkey and pubkey.startswith(pubkey_prefix.lower()):
                lat = attrs.get("adv_lat") or attrs.get("latitude")
                lon = attrs.get("adv_lon") or attrs.get("longitude")
                
                if lat and lon:
                    matches.append({
                        "name": attrs.get("adv_name", "Unknown"),
                        "lat": float(lat),
                        "lon": float(lon),
                        "pubkey": pubkey,
                        "node_type": attrs.get("node_type_str", "Unknown").lower(),
                        "last_advert": attrs.get("last_advert", 0),
                    })
        
        if not matches:
            return None
        
        if len(matches) == 1:
            return matches[0]
        
        # Prefer repeaters, then most recent
        repeaters = [m for m in matches if "repeater" in m["node_type"]]
        if repeaters:
            repeaters.sort(key=lambda x: x["last_advert"], reverse=True)
            return repeaters[0]
        
        matches.sort(key=lambda x: x["last_advert"], reverse=True)
        return matches[0]
