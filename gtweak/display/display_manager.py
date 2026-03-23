# Copyright (c) 2026 MRH0
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

"""
Display manager for gnome-tweaks.
Supports multiple displays via Mutter DisplayConfig DBus API (Wayland only).
Handles resolution/framerate configuration, display modes, HDR toggle, and primary display selection.
"""

import json
import logging
import os
from typing import List, Tuple, Optional, Dict, Any
from enum import IntEnum

try:
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio, GLib
except (ImportError, ValueError):
    Gio = None
    GLib = None

logger = logging.getLogger(__name__)


class DisplayMode(IntEnum):
    """Display modes for multiple displays"""
    EXTEND = 0  # Extend display
    MIRROR = 1  # Mirror display
    PRIMARY = 2  # Set as primary
    OFF = 3  # Turn off


class DisplayConnectorType(str):
    """Display connector types"""
    HDMI = "HDMI"
    DP = "DP"
    VGA = "VGA"
    LVDS = "LVDS"
    eDP = "eDP"  # Embedded display panel
    VIRTUAL = "Virtual"  # For virtual displays


class DBusDisplayManager:
    """
    Display manager for Wayland using Mutter DisplayConfig DBus API.
    Provides full display configuration support via DBus.
    """
    
    BUS_NAME = "org.gnome.Mutter.DisplayConfig"
    OBJECT_PATH = "/org/gnome/Mutter/DisplayConfig"
    INTERFACE = "org.gnome.Mutter.DisplayConfig"
    
    def __init__(self):
        """Initialize DBus display manager"""
        self.mutter_proxy = None
        self.bus = None
        self.connected = False
        self._modes_cache = {}  # Cache of mode data
        self._service_available = False
        
        if Gio is None:
            logger.error("DBusDisplayManager: GIO not available")
            return
        
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self.mutter_proxy = Gio.DBusProxy.new_sync(
                self.bus,
                Gio.DBusProxyFlags.NONE,
                None,
                self.BUS_NAME,
                self.OBJECT_PATH,
                self.INTERFACE,
                None
            )
            # Check if the service is actually available
            try:
                # Try a simple call to verify service is available
                self.mutter_proxy.call_sync(
                    "GetCurrentState",
                    None,
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None
                )
                self._service_available = True
                self.connected = True
                logger.info("DBusDisplayManager: Connected to Mutter DisplayConfig DBus")
            except GLib.GError as ge:
                if "ServiceUnknown" in str(ge):
                    logger.warning("DBusDisplayManager: Mutter DisplayConfig service not available. "
                                 "This is normal in containerized/Flatpak environments. "
                                 "Display control requires a running Wayland compositor with DBus support.")
                    self._service_available = False
                    self.connected = False
                else:
                    raise
        except Exception as e:
            logger.error(f"DBusDisplayManager: Failed to connect to DBus: {type(e).__name__}: {e}")
            self.connected = False
            self._service_available = False
    
    def is_available(self) -> bool:
        """Check if display manager is available"""
        return self.connected and self.mutter_proxy is not None
    
    def get_displays(self) -> List[Dict[str, Any]]:
        """
        Get list of available displays using Mutter DisplayConfig GetResources.
        Parses the complex DBus response to extract display names, resolutions, and framerates.
        
        Returns:
            List of dicts with: name, connected, primary, resolution, framerate, modes
        """
        if not self.is_available():
            if not self._service_available:
                logger.warning("DBusDisplayManager: Mutter DisplayConfig service not available - "
                             "display control not accessible in this environment")
            else:
                logger.error("DBusDisplayManager: Manager not available")
            return []
        
        try:
            # Call GetResources to get all display information
            result = self.mutter_proxy.call_sync(
                "GetResources",
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            
            if not result:
                logger.error("DBusDisplayManager: GetResources returned empty result")
                return []
            
            items = result.unpack()
            if len(items) < 4:
                logger.error(f"DBusDisplayManager: GetResources returned unexpected data (got {len(items)} items)")
                return []
            
            # GetResources returns: (serial, crtcs, logical_monitors, modes, ...)
            serial = items[0]
            crtcs = items[1]
            logical_monitors = items[2]
            modes_data = items[3]
            
            logger.debug(f"DBusDisplayManager: GetResources - serial={serial}, crtcs={len(crtcs)}, "
                        f"logical_monitors={len(logical_monitors)}, modes={len(modes_data)}")
            
            # Build modes cache for quick lookup by mode index
            # Modes are indexed 0...N and each has (index, unknown, width, height, refresh_rate, unknown)
            self._modes_cache = {}
            for mode_idx, mode_tuple in enumerate(modes_data):
                if isinstance(mode_tuple, (tuple, list)) and len(mode_tuple) >= 5:
                    width = mode_tuple[2]
                    height = mode_tuple[3]
                    # Refresh rate is in Hz already (or needs conversion)
                    refresh_rate = float(mode_tuple[4])
                    self._modes_cache[mode_idx] = {
                        'width': width,
                        'height': height,
                        'refresh_rate': refresh_rate
                    }
            
            logger.debug(f"DBusDisplayManager: Cached {len(self._modes_cache)} modes")
            
            # Process logical monitors (these have display names and current configuration)
            displays = []
            for logical_idx, logical_monitor in enumerate(logical_monitors):
                try:
                    if len(logical_monitor) < 6:
                        logger.debug(f"DBusDisplayManager: Logical monitor {logical_idx} has incomplete data")
                        continue
                    
                    # Logical monitor structure from DBus:
                    # [0] = x position
                    # [1] = y position  
                    # [2] = scale
                    # [3] = crtc_indices (list)
                    # [4] = display_name (string)
                    # [5] = mode_indices (list of indices into modes array)
                    # [6] = empty list
                    # [7] = properties_dict with 'primary' key
                    
                    x_pos = logical_monitor[0]
                    y_pos = logical_monitor[1]
                    crtc_indices = logical_monitor[3] if len(logical_monitor) > 3 else []
                    display_name = logical_monitor[4]
                    mode_indices = logical_monitor[5] if len(logical_monitor) > 5 else []
                    properties = logical_monitor[7] if len(logical_monitor) > 7 else {}
                    is_primary = properties.get('primary', False) if isinstance(properties, dict) else False
                    
                    # Get current mode (first or primary mode)
                    current_resolution = None
                    current_framerate = None
                    if crtc_indices and len(crtc_indices) > 0:
                        crtc_idx = crtc_indices[0]
                        if crtc_idx < len(crtcs):
                            crtc = crtcs[crtc_idx]
                            if len(crtc) > 1:
                                current_mode_idx = crtc[1]  # Mode index in crtc
                                if current_mode_idx in self._modes_cache:
                                    mode_data = self._modes_cache[current_mode_idx]
                                    current_resolution = f"{mode_data['width']}x{mode_data['height']}"
                                    current_framerate = mode_data['refresh_rate']
                    
                    # Get available modes for this display
                    available_modes = []
                    logger.debug(f"DBusDisplayManager: Processing display '{display_name}': "
                               f"mode_indices={mode_indices}, num_modes_in_cache={len(self._modes_cache)}")
                    if mode_indices:
                        for mode_idx in mode_indices:
                            if mode_idx in self._modes_cache:
                                mode_data = self._modes_cache[mode_idx]
                                res_str = f"{mode_data['width']}x{mode_data['height']}"
                                available_modes.append({
                                    'resolution': res_str,
                                    'framerate': mode_data['refresh_rate']
                                })
                                logger.debug(f"  Added mode: {res_str} @ {mode_data['refresh_rate']}Hz")
                            else:
                                logger.debug(f"  Mode index {mode_idx} not in cache (cache has {list(self._modes_cache.keys())})")
                    else:
                        logger.debug(f"  No mode_indices for display '{display_name}'")
                    
                    display = {
                        'name': display_name,
                        'connected': True,
                        'primary': is_primary,
                        'resolution': current_resolution,
                        'framerate': current_framerate,
                        'modes': available_modes,
                        'x': x_pos,
                        'y': y_pos
                    }
                    
                    displays.append(display)
                    logger.debug(f"DBusDisplayManager: Added display '{display_name}' - "
                               f"resolution={current_resolution}, framerate={current_framerate}Hz, "
                               f"primary={is_primary}, available_modes={len(available_modes)}")
                
                except (IndexError, KeyError, TypeError) as e:
                    logger.debug(f"DBusDisplayManager: Error parsing logical monitor {logical_idx}: {e}")
                    continue
            
            logger.info(f"DBusDisplayManager: Found {len(displays)} displays")
            return displays
        
        except GLib.GError as ge:
            # Handle GLib DBus errors specifically
            if "ServiceUnknown" in str(ge):
                if not self._service_available:
                    logger.debug("DBusDisplayManager: Mutter service is not available")
                else:
                    logger.warning("DBusDisplayManager: Lost connection to Mutter DisplayConfig service")
                    self._service_available = False
            else:
                logger.error(f"DBusDisplayManager.get_displays: DBus error: {type(ge).__name__}: {ge}")
            return []
        except Exception as e:
            logger.error(f"DBusDisplayManager.get_displays: {type(e).__name__}: {e}")
            return []
    
    def get_primary_display(self) -> Optional[str]:
        """Get the name of the primary display"""
        displays = self.get_displays()
        for display in displays:
            if display['primary']:
                logger.debug(f"Primary display: {display['name']}")
                return display['name']
        return None
    
    def set_primary_display(self, display_name: str) -> bool:
        """Set a display as primary via DBus ApplyMonitorsConfig"""
        logger.warning(f"DBusDisplayManager.set_primary_display: Not yet implemented")
        return False
    
    def set_resolution(self, display_name: str, width: int, height: int) -> bool:
        """Set display resolution via DBus"""
        logger.warning(f"DBusDisplayManager.set_resolution: Not yet implemented")
        return False
    
    def set_framerate(self, display_name: str, width: int, height: int, framerate: float) -> bool:
        """Set display framerate via DBus"""
        logger.warning(f"DBusDisplayManager.set_framerate: Not yet implemented")
        return False
    
    def set_display_mode(self, display_names: List[str], mode: DisplayMode) -> bool:
        """Set display mode (extend, mirror, etc) via DBus"""
        logger.warning(f"DBusDisplayManager.set_display_mode: Not yet implemented")
        return False
    
    def toggle_hdr(self, display_name: str, enabled: bool) -> bool:
        """Toggle HDR for a display via DBus"""
        logger.warning(f"DBusDisplayManager.toggle_hdr: Not yet implemented")
        return False


def get_display_manager() -> Optional[DBusDisplayManager]:
    """
    Get the display manager instance for Wayland.
    Only supports Wayland with Mutter DisplayConfig DBus.
    Returns None if not available (e.g., in containerized environments).
    """
    xdg_session = os.environ.get('XDG_SESSION_TYPE', '').lower()
    
    if 'wayland' not in xdg_session:
        logger.warning("get_display_manager: This application requires Wayland")
        return None
    
    if Gio is None:
        logger.error("get_display_manager: GIO library not available")
        return None
    
    mgr = DBusDisplayManager()
    if mgr.is_available():
        logger.info("get_display_manager: Using Mutter DisplayConfig DBus")
        return mgr
    elif not mgr._service_available:
        logger.warning("get_display_manager: Mutter DisplayConfig service not available. "
                      "This is expected in containerized environments (Docker, Flatpak, etc). "
                      "Display configuration will not be available.")
        return mgr  # Return manager but it won't have display data
    else:
        logger.error("get_display_manager: Mutter DisplayConfig DBus not available")
        return mgr
