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
        self._serial = 0  # Current DBus serial for applying changes
        self._displays_info_cache = None  # Cache of full display info including connectors
        
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
    
    def get_raw_resources(self) -> Optional[Any]:
        """
        Get raw DBus response for diagnostics.
        Returns the unpacked GetResources response or None if unavailable.
        """
        if not self.is_available():
            logger.warning("Display manager not available")
            return None
        
        try:
            result = self.mutter_proxy.call_sync(
                "GetResources",
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            if result:
                return result.unpack()
        except Exception as e:
            logger.error(f"Failed to get raw resources: {e}")
        return None
    
    def get_displays(self) -> List[Dict[str, Any]]:
        """
        Get list of available displays using Mutter DisplayConfig GetResources.
        Parses the complex DBus response to extract display names, resolutions, and framerates.
        
        Returns:
            List of dicts with: name, connected, primary, resolution, framerate, modes, connector, mode_idx
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
            logger.debug(f"DBusDisplayManager: GetResources returned {len(items)} items")
            
            if len(items) < 4:
                logger.error(f"DBusDisplayManager: GetResources returned unexpected data (got {len(items)} items, expected >= 4)")
                return []
            
            # GetResources returns: (serial, crtcs, logical_monitors, modes, ...)
            # NOTE: The structure is different - connectors are embedded in logical_monitors, not separate
            serial = items[0]
            crtcs = items[1] if isinstance(items[1], (list, tuple)) else []
            logical_monitors = items[2] if isinstance(items[2], (list, tuple)) else []
            modes_data = items[3] if isinstance(items[3], (list, tuple)) else []
            
            self._serial = serial
            
            logger.debug(f"DBusDisplayManager: GetResources - serial={serial}, crtcs={len(crtcs)}, "
                        f"logical_monitors={len(logical_monitors)}, modes={len(modes_data)}")
            
            # Build modes cache for quick lookup by mode index
            # Modes format: (?, ?, width, height, refresh_rate, ...)
            # The first 2 elements are metadata, actual resolution starts at index 2
            self._modes_cache = {}
            for mode_idx, mode_tuple in enumerate(modes_data):
                if isinstance(mode_tuple, (tuple, list)) and len(mode_tuple) >= 5:
                    try:
                        # Skip first 2 elements, actual data starts at index 2
                        width = int(mode_tuple[2])
                        height = int(mode_tuple[3])
                        # Refresh rate might be in mHz (thousandths of Hz), convert if needed
                        refresh_rate = float(mode_tuple[4])
                        if refresh_rate > 1000:  # Likely in mHz, convert to Hz
                            refresh_rate = refresh_rate / 1000.0
                        
                        self._modes_cache[mode_idx] = {
                            'width': width,
                            'height': height,
                            'refresh_rate': refresh_rate
                        }
                        
                        # Debug: log some key modes
                        if mode_idx in (0, 1, 353, 354) or (width > 1920):
                            logger.debug(f"  Mode {mode_idx}: {width}x{height} @ {refresh_rate}Hz (raw: {mode_tuple[:5]})")
                    except (ValueError, TypeError, IndexError) as e:
                        logger.debug(f"  Error parsing mode {mode_idx}: {e}")
                        continue
                    except (ValueError, TypeError, IndexError) as e:
                        logger.debug(f"  Error parsing mode {mode_idx}: {e}")
                        continue
            
            logger.debug(f"DBusDisplayManager: Cached {len(self._modes_cache)} modes")
            
            # Process logical monitors
            # NEW STRUCTURE: connectors are embedded in logical_monitors!
            # Logical monitor format: (x, y, scale, [crtc_indices], connector_name, [mode_indices], {properties})
            displays = []
            for logical_idx, logical_monitor in enumerate(logical_monitors):
                try:
                    if not isinstance(logical_monitor, (tuple, list)):
                        logger.debug(f"Logical monitor {logical_idx} is not a tuple/list, skipping")
                        continue
                    
                    if len(logical_monitor) < 5:
                        logger.debug(f"Logical monitor {logical_idx} has incomplete data ({len(logical_monitor)} elements)")
                        continue
                    
                    # NEW structure from recent Ubuntu/GNOME versions:
                    # [0] = PRIMARY CRTC INDEX (points to the specific CRTC for this monitor!)
                    # [1] = unknown large integer
                    # [2] = transform/rotation
                    # [3] = crtc_indices (list)
                    # [4] = connector_name (STRING)
                    # [5] = supported_mode_indices (list)
                    # [6] = unknown (empty list in current format)
                    # [7] = properties dict
                    
                    # CRITICAL FIX: logical_monitor[0] IS the CRTC index for THIS monitor!
                    # CRTC structure: [id, ?, x, y, width, height, ...]
                    
                    if len(logical_monitor) < 8:
                        logger.debug(f"Logical monitor {logical_idx} has fewer than 8 elements ({len(logical_monitor)}), trying to parse anyway")
                    
                    transform = int(logical_monitor[2]) if len(logical_monitor) > 2 else 0
                    # Scale should come from somewhere else - for now default to 1.0
                    scale = 1.0
                    crtc_indices = logical_monitor[3] if isinstance(logical_monitor[3], (list, tuple)) else []
                    connector_name = str(logical_monitor[4]) if len(logical_monitor) > 4 else "Unknown"
                    
                    # Get X,Y position from the PRIMARY CRTC indicated by logical_monitor[0]
                    x_pos = 0
                    y_pos = 0
                    primary_crtc_idx = int(logical_monitor[0])
                    if primary_crtc_idx >= 0 and primary_crtc_idx < len(crtcs):
                        crtc = crtcs[primary_crtc_idx]
                        if isinstance(crtc, (tuple, list)) and len(crtc) >= 4:
                            try:
                                x_pos = int(crtc[2])  # CRTC[2] = X position
                                y_pos = int(crtc[3])  # CRTC[3] = Y position
                                logger.debug(f"  Retrieved position from primary CRTC {primary_crtc_idx}: ({x_pos}, {y_pos})")
                            except (ValueError, TypeError) as e:
                                logger.debug(f"  Error reading CRTC position: {e}")
                                x_pos = 0
                                y_pos = 0
                    supported_modes = logical_monitor[5] if isinstance(logical_monitor[5], (list, tuple)) else []
                    properties = logical_monitor[7] if isinstance(logical_monitor[7], dict) and len(logical_monitor) > 7 else logical_monitor[6] if isinstance(logical_monitor[6], dict) else {}
                    
                    # LOG ALL FIELDS FOR DEBUGGING
                    logger.debug(f"Logical monitor {logical_idx} RAW DATA (first 8 elements):")
                    for idx in range(min(8, len(logical_monitor))):
                        item = logical_monitor[idx]
                        if isinstance(item, (list, tuple)):
                            logger.debug(f"  [{idx}]: list/tuple with {len(item)} items, first: {item[0] if item else 'empty'}")
                        elif isinstance(item, dict):
                            logger.debug(f"  [{idx}]: dict with keys: {list(item.keys())[:5]}")
                        else:
                            logger.debug(f"  [{idx}]: {type(item).__name__} = {item}")
                    
                    logger.debug(f"Logical monitor {logical_idx}: x={x_pos}, y={y_pos}, "
                               f"connector={connector_name}, supported_modes={len(supported_modes)}, props_keys={list(properties.keys())[:5]}")
                    
                    # Get primary status from properties
                    is_primary = properties.get('primary', False)
                    
                    # Get current resolution from properties if available
                    # Otherwise use the BEST (largest) supported mode
                    current_resolution = None
                    current_framerate = None
                    physical_width = 0
                    physical_height = 0
                    mode_idx = None
                    
                    # Get physical dimensions from primary CRTC
                    # CRTC structure: [id, ?, x, y, width, height, ...]
                    if primary_crtc_idx >= 0 and primary_crtc_idx < len(crtcs):
                        crtc = crtcs[primary_crtc_idx]
                        if isinstance(crtc, (tuple, list)) and len(crtc) >= 6:
                            try:
                                physical_width = int(crtc[4])   # CRTC[4] = width
                                physical_height = int(crtc[5])  # CRTC[5] = height
                                logger.debug(f"  Retrieved physical dimensions from primary CRTC {primary_crtc_idx}: {physical_width}x{physical_height}")
                            except (ValueError, TypeError) as e:
                                logger.debug(f"  Error reading CRTC dimensions: {e}")
                    
                    # Find the best mode (largest resolution)
                    best_mode_idx = None
                    best_area = 0
                    for m_idx in supported_modes:
                        if m_idx in self._modes_cache:
                            mode_data = self._modes_cache[m_idx]
                            area = mode_data['width'] * mode_data['height']
                            if area > best_area:
                                best_area = area
                                best_mode_idx = m_idx
                    
                    if best_mode_idx is not None:
                        mode_idx = best_mode_idx
                        mode_data = self._modes_cache[mode_idx]
                        current_resolution = f"{mode_data['width']}x{mode_data['height']}"
                        current_framerate = mode_data['refresh_rate']
                        # If we already got dimensions from CRTC, prefer those; otherwise use mode data
                        if physical_width == 0 or physical_height == 0:
                            physical_width = mode_data['width']
                            physical_height = mode_data['height']
                        logger.debug(f"  Using best mode {mode_idx}: {current_resolution} @ {current_framerate}Hz")
                    
                    # Expand mode indices into full mode dicts for compatibility with existing code
                    expanded_modes = []
                    for m_idx in supported_modes:
                        if m_idx in self._modes_cache:
                            mode_data = self._modes_cache[m_idx]
                            expanded_modes.append({
                                'resolution': f"{mode_data['width']}x{mode_data['height']}",
                                'framerate': mode_data['refresh_rate'],
                                'width': mode_data['width'],
                                'height': mode_data['height'],
                                'index': m_idx
                            })
                    
                    display = {
                        'name': connector_name,
                        'connector': connector_name,
                        'connected': True,
                        'primary': is_primary,
                        'resolution': current_resolution,
                        'framerate': current_framerate,
                        'modes': expanded_modes,
                        'x': x_pos,
                        'y': y_pos,
                        'scale': scale,
                        'mode_idx': mode_idx,
                        'physical_width': physical_width,
                        'physical_height': physical_height,
                        'properties': properties
                    }
                    
                    displays.append(display)
                    logger.debug(f"Added display: {connector_name} at ({x_pos}, {y_pos}), "
                               f"resolution={current_resolution}, primary={is_primary}, "
                               f"modes={len(expanded_modes)}")
                
                except (IndexError, KeyError, TypeError, ValueError) as e:
                    logger.debug(f"Error parsing logical monitor {logical_idx}: {type(e).__name__}: {e}")
                    continue
            
            self._displays_info_cache = displays
            logger.info(f"DBusDisplayManager: Found {len(displays)} displays")
            return displays
        
        except GLib.GError as ge:
            if "ServiceUnknown" in str(ge):
                if not self._service_available:
                    logger.debug("DBusDisplayManager: Mutter service is not available")
                else:
                    logger.warning("DBusDisplayManager: Lost connection to Mutter DisplayConfig service")
                    self._service_available = False
            else:
                logger.error(f"DBusDisplayManager.get_displays: DBus error: {type(ge).__name__}: {ge}")
            return []
        except TypeError as te:
            logger.error(f"DBusDisplayManager.get_displays: TypeError: {te}")
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
    
    def apply_display_arrangement(self, arrangement: List[Dict[str, Any]]) -> bool:
        """
        Apply display arrangement configuration via DBus ApplyMonitorsConfig.
        
        Args:
            arrangement: List of dicts with display configuration:
                {
                    'connector': 'HDMI-1',
                    'x': 0,
                    'y': 0,
                    'mode_idx': 0,
                    'scale': 1.0,
                    'transform': 0,
                    'primary': False
                }
        
        Returns:
            True if configuration was applied successfully
        """
        if not self.is_available():
            logger.error("DBusDisplayManager.apply_display_arrangement: Manager not available")
            return False
        
        try:
            # Refresh displays to get current state
            self.get_displays()
            
            # Build logical monitors array for DBus
            # Expected format per Mutter DisplayConfig:
            # a(iiduba(ssa{sv})) - array of monitors, each with:
            #   i = x position (int32)
            #   i = y position (int32)
            #   d = scale (double)
            #   u = transform (uint32)
            #   b = primary (boolean)
            #   a(ssa{sv}) = array of outputs (connectors):
            #     s = connector_name
            #     s = mode_name in format "WIDTHxHEIGHT@REFRESH_RATE" (e.g., "2560x1440@60")
            #     a{sv} = properties
            logical_monitors = []
            logger.debug(f"=== DISPLAY ARRANGEMENT DEBUG ===")
            logger.debug(f"Input arrangement count: {len(arrangement)}")
            
            for idx, config in enumerate(arrangement):
                connector = config.get('connector')
                x = int(config.get('x', 0))
                y = int(config.get('y', 0))
                scale = float(config.get('scale', 1.0))
                transform = int(config.get('transform', 0))
                primary = bool(config.get('primary', False))
                mode_idx = int(config.get('mode_idx', 0))
                
                logger.debug(f"  [{idx}] {connector}: pos=({x}, {y}), scale={scale}, "
                           f"transform={transform}, primary={primary}, mode_idx={mode_idx}")
                
                # Find connector and get mode name in correct format
                displays = self._displays_info_cache or self.get_displays()
                display = next((d for d in displays if d['connector'] == connector), None)
                
                if not display:
                    logger.warning(f"Connector '{connector}' not found in display info")
                    continue
                
                # Build mode name in format "WIDTHxHEIGHT@REFRESH_RATE"
                # Get mode data from cache
                mode_name = "1024x768@60"  # Default fallback
                if mode_idx in self._modes_cache:
                    mode_data = self._modes_cache[mode_idx]
                    width = mode_data['width']
                    height = mode_data['height']
                    refresh = mode_data['refresh_rate']
                    # Format refresh rate with 3 decimal places (e.g., "179.877" not "179.877197265625")
                    mode_name = f"{width}x{height}@{refresh:.3f}"
                
                # Build monitor in correct format:
                # [x, y, scale, transform, primary, [[connector_name, mode_name, {}]]]
                logical_monitor = (
                    x,
                    y,
                    scale,
                    transform,
                    primary,
                    [[connector, mode_name, {}]]  # Array of outputs with mode name format
                )
                logical_monitors.append(logical_monitor)
                
                logger.debug(f"  → DBus format: x={x}, y={y}, scale={scale}, "
                           f"transform={transform}, primary={primary}, mode={mode_name}")
            
            if not logical_monitors:
                logger.error("No valid logical monitors to apply")
                return False
            
            # Call ApplyMonitorsConfig with method=1 (persistent)
            # Signature: (serial, method, array_of_monitors, options_dict)
            # array_of_monitors signature: a(iiduba(ssa{sv}))
            method = 1  # 1 = persistent, 0 = verify, 2 = temporary
            options_dict = {}  # Additional options (usually empty)
            
            logger.info(f"=== APPLYING MONITOR CONFIGURATION ===")
            logger.info(f"Serial: {self._serial}")
            logger.info(f"Method: {method} (1=persistent)")
            logger.info(f"Number of monitors: {len(logical_monitors)}")
            for i, mon in enumerate(logical_monitors):
                logger.info(f"  Monitor {i}: x={mon[0]}, y={mon[1]}, scale={mon[2]}, "
                          f"transform={mon[3]}, primary={mon[4]}, connectors={mon[5]}")
            
            result = self.mutter_proxy.call_sync(
                "ApplyMonitorsConfig",
                GLib.Variant("(uua(iiduba(ssa{sv}))a{sv})",
                            (self._serial, method, logical_monitors, options_dict)),
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            
            # ApplyMonitorsConfig typically returns empty/None on success
            # The absence of an exception means the call succeeded
            logger.info("Display configuration applied successfully")
            return True
        
        except GLib.GError as ge:
            logger.error(f"DBusDisplayManager.apply_display_arrangement: DBus error: {type(ge).__name__}: {ge}")
            return False
        except Exception as e:
            logger.error(f"DBusDisplayManager.apply_display_arrangement: {type(e).__name__}: {e}")
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
