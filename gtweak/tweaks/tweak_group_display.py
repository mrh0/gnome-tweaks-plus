# Copyright (c) 2026 MRH0
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import logging
import os
from typing import List, Optional
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, Pango

from gtweak.tweakmodel import Tweak, TweakGroup
from gtweak.widgets import (
    TweakPreferencesPage,
    TweakPreferencesGroup,
    GSettingsTweakSwitchRow,
    build_list_store,
    TweakListStoreItem,
    _GSettingsTweak,
    _DependableMixin,
)
from gtweak.display.display_manager import (
    get_display_manager,
    DisplayMode,
)
from gtweak.display.screen_arrangement import ScreenArrangementWidget

logger = logging.getLogger(__name__)

# Set up translation function - gets injected by framework, provide fallback
try:
    _
except NameError:
    def _(msg):
        """Translation wrapper - fallback"""
        return msg


# ===== ADVANCED DISPLAY SETTINGS =====

class DisplaySelectorRow(Adw.ComboRow, Tweak):
    """Combo row for selecting which display to configure"""
    
    def __init__(self, on_display_changed=None, **options):
        Tweak.__init__(
            self,
            title=_("Select Display"),
            description=_("Choose which display to configure"),
            **options
        )
        
        Adw.ComboRow.__init__(
            self,
            title=_("Select Display"),
            subtitle=_("Select a display to view and modify its settings")
        )
        
        self.display_mgr = get_display_manager()
        self.on_display_changed = on_display_changed
        self._updating = False
        self.loaded = self.display_mgr is not None
        
        if not self.loaded:
            logger.warning("DisplaySelectorRow: Display manager not available")
            return
        
        # Build list of displays
        self._refresh_displays()
        
        # Connect signals
        self.connect("notify::selected-item", self._on_selection_changed)
        
        self.widget_for_size_group = None
    
    def _refresh_displays(self):
        """Refresh list of available displays"""
        displays = self.display_mgr.get_displays()
        connected = [d for d in displays if d['connected']]
        
        display_items = [d['name'] for d in connected]
        
        model = build_list_store([
            (name, name)
            for name in display_items
        ])
        
        # Set up factory BEFORE setting model
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._factory_setup)
        factory.connect("bind", self._factory_bind)
        self.set_factory(factory)
        
        self.set_model(model)
        
        if display_items:
            self.set_selected(0)
    
    def _factory_setup(self, factory, item):
        """Set up list item factory"""
        label = Gtk.Label(xalign=0.0, ellipsize=Pango.EllipsizeMode.END, 
                         max_width_chars=30, valign=Gtk.Align.CENTER)
        item.set_child(label)
    
    def _factory_bind(self, factory, item):
        """Bind data to list item"""
        label = item.get_child()
        label.set_label(item.get_item().title)
    
    def _on_selection_changed(self, combo, param):
        """Handle display selection change"""
        if self._updating:
            return
        
        item = combo.get_selected_item()
        if item and self.on_display_changed:
            self.on_display_changed(item.title)
    
    def get_selected_display(self) -> Optional[str]:
        """Get the currently selected display name"""
        item = self.get_selected_item()
        if item:
            return item.title
        return None


class PrimaryDisplayToggle(Adw.ActionRow, Tweak):
    """Toggle to set a display as primary"""
    
    def __init__(self, display_name: Optional[str] = None, **options):
        Adw.ActionRow.__init__(self)
        Tweak.__init__(
            self,
            title=_("Set as Primary"),
            description=_("Make this the main/primary display"),
            **options
        )
        
        self.set_title(_("Set as Primary"))
        self.display_mgr = get_display_manager()
        self.display_name = display_name
        self.loaded = self.display_mgr is not None
        self._updating = False
        
        if not self.loaded:
            return
        
        # Create switch widget
        switch = Gtk.Switch(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self._update_switch_from_state(switch)
        
        switch.connect("notify::active", self._on_switch_changed)
        self.add_suffix(switch)
        self.set_activatable_widget(switch)
        
        self._switch = switch
    
    def set_display(self, name: str):
        """Set which display to control"""
        self.display_name = name
        if self._switch:
            self._update_switch_from_state(self._switch)
    
    def _update_switch_from_state(self, switch):
        """Update switch based on current primary display"""
        try:
            primary = self.display_mgr.get_primary_display()
            is_primary = (primary == self.display_name)
            self._updating = True
            switch.set_active(is_primary)
            self._updating = False
        except Exception as e:
            logger.error(f"Error updating primary display switch: {e}")
            switch.set_active(False)
    
    def _on_switch_changed(self, switch, param):
        """Handle switch toggle"""
        if self._updating or not self.display_name:
            return
        
        try:
            if switch.get_active():
                self._updating = True
                if self.display_mgr.set_primary_display(self.display_name):
                    logger.info(f"Set {self.display_name} as primary")
                else:
                    switch.set_active(False)
                self._updating = False
        except Exception as e:
            logger.error(f"Error setting primary display: {e}")
            self._updating = True
            switch.set_active(False)
            self._updating = False


class ResolutionSelector(Adw.ComboRow, Tweak):
    """Combo row for selecting display resolution"""
    
    def __init__(self, on_resolution_changed=None, **options):
        Tweak.__init__(
            self,
            title=_("Resolution"),
            description=_("Set display resolution"),
            **options
        )
        
        Adw.ComboRow.__init__(
            self,
            title=_("Resolution"),
            subtitle=_("Select display resolution")
        )
        
        self.display_mgr = get_display_manager()
        self.display_name: Optional[str] = None
        self.on_resolution_changed = on_resolution_changed
        self.loaded = self.display_mgr is not None
        self._updating = False
        
        if self.loaded:
            self.connect("notify::selected-item", self._on_resolution_changed)
        
        self.widget_for_size_group = None
    
    def set_display(self, name: str):
        """Set which display to control"""
        self.display_name = name
        self._refresh_resolutions()
    
    def _refresh_resolutions(self):
        """Refresh available resolutions for current display"""
        if not self.display_name:
            return
        
        try:
            displays = self.display_mgr.get_displays()
            display = next((d for d in displays if d['name'] == self.display_name), None)
            
            if not display:
                logger.warning(f"Display {self.display_name} not found")
                return
            
            # Get unique resolutions
            resolutions = []
            for mode in display['modes']:
                if mode['resolution'] not in resolutions:
                    resolutions.append(mode['resolution'])
            
            model = build_list_store([
                (res, res)
                for res in resolutions
            ])
            
            # Set up factory BEFORE setting model
            factory = Gtk.SignalListItemFactory()
            factory.connect("setup", self._factory_setup)
            factory.connect("bind", self._factory_bind)
            self.set_factory(factory)
            
            self.set_model(model)
            
            # Set current selection
            if display['resolution']:
                for i, res in enumerate(resolutions):
                    if res == display['resolution']:
                        self.set_selected(i)
                        break
        
        except Exception as e:
            logger.error(f"Error refreshing resolutions: {e}")
    
    def _factory_setup(self, factory, item):
        """Set up list item factory"""
        label = Gtk.Label(xalign=0.0)
        item.set_child(label)
    
    def _factory_bind(self, factory, item):
        """Bind data to list item"""
        label = item.get_child()
        label.set_label(item.get_item().title)
    
    def _on_resolution_changed(self, combo, param):
        """Handle resolution selection change"""
        if self._updating or not self.display_name:
            return
        
        try:
            item = combo.get_selected_item()
            if item:
                res = item.title
                width, height = map(int, res.split('x'))
                
                self._updating = True
                if self.display_mgr.set_resolution(self.display_name, width, height):
                    logger.info(f"Set {self.display_name} resolution to {res}")
                    # Notify listener about resolution change
                    if self.on_resolution_changed:
                        self.on_resolution_changed(res)
                self._updating = False
        except Exception as e:
            logger.error(f"Error setting resolution: {e}")
            self._updating = False


class FramerateSelector(Adw.ComboRow, Tweak):
    """Combo row for selecting display framerate/refresh rate"""
    
    def __init__(self, display_name: Optional[str] = None, **options):
        Tweak.__init__(
            self,
            title=_("Refresh Rate"),
            description=_("Set display refresh rate (Hz)"),
            **options
        )
        
        Adw.ComboRow.__init__(
            self,
            title=_("Refresh Rate"),
            subtitle=_("Select display refresh rate")
        )
        
        self.display_mgr = get_display_manager()
        self.display_name = display_name
        self.current_resolution = None
        self.loaded = self.display_mgr is not None
        self._updating = False
        
        if self.loaded:
            self._refresh_framerates()
            self.connect("notify::selected-item", self._on_framerate_changed)
        
        self.widget_for_size_group = None
    
    def set_display(self, name: str, resolution: Optional[str] = None):
        """Set which display and resolution to control"""
        self.display_name = name
        if resolution:
            self.current_resolution = resolution
        self._refresh_framerates()
    
    def _refresh_framerates(self):
        """Refresh available framerates for current display and resolution"""
        if not self.display_name:
            return
        
        try:
            displays = self.display_mgr.get_displays()
            display = next((d for d in displays if d['name'] == self.display_name), None)
            
            if not display:
                logger.warning(f"Display {self.display_name} not found")
                # Set empty model so widget displays properly
                self.set_model(Gio.ListStore())
                return
            
            # Use current resolution or first available
            res = self.current_resolution or display['resolution']
            logger.debug(f"FramerateSelector: Searching for framerates for {self.display_name} at {res}")
            logger.debug(f"  Available modes in display: {display['modes']}")
            
            # Collect all framerates for this resolution
            # Handle both old format (with 'framerates' list) and new format (with individual 'framerate' values)
            framerates = set()
            for mode in display['modes']:
                logger.debug(f"  Checking mode: {mode}")
                if mode['resolution'] == res:
                    # New format: each mode has a single 'framerate'
                    if 'framerate' in mode and mode['framerate'] is not None:
                        framerates.add(float(mode['framerate']))
                        logger.debug(f"    → Added framerate: {mode['framerate']}")
                    # Old format: mode has 'framerates' list
                    elif 'framerates' in mode:
                        framerates.update(mode['framerates'])
                        logger.debug(f"    → Added framerates: {mode['framerates']}")
            
            framerates = sorted(framerates, reverse=True)
            logger.debug(f"  Total framerates found: {framerates}")
            
            # Build model with available framerates
            model = build_list_store([
                (str(fr), f"{fr:.2f} Hz")
                for fr in framerates
            ])
            
            # Set up factory BEFORE setting model
            factory = Gtk.SignalListItemFactory()
            factory.connect("setup", self._factory_setup)
            factory.connect("bind", self._factory_bind)
            self.set_factory(factory)
            
            self.set_model(model)
            
            if not framerates:
                logger.warning(f"No framerates found for {self.display_name} at {res}")
                return
            
            # Set current framerate
            if display['framerate']:
                for i, fr in enumerate(framerates):
                    if abs(fr - display['framerate']) < 0.5:  # Allow small floating point diff
                        self._updating = True
                        self.set_selected(i)
                        self._updating = False
                        break
        
        except Exception as e:
            logger.error(f"Error refreshing framerates: {e}", exc_info=True)
    
    def _factory_setup(self, factory, item):
        """Set up list item factory"""
        label = Gtk.Label(xalign=0.0)
        item.set_child(label)
    
    def _factory_bind(self, factory, item):
        """Bind data to list item"""
        label = item.get_child()
        label.set_label(item.get_item().title)
    
    def _on_framerate_changed(self, combo, param):
        """Handle framerate selection change"""
        if self._updating or not self.display_name or not self.current_resolution:
            return
        
        try:
            item = combo.get_selected_item()
            if item:
                framerate = float(item.value)
                width, height = map(int, self.current_resolution.split('x'))
                
                self._updating = True
                if self.display_mgr.set_framerate(self.display_name, width, height, framerate):
                    logger.info(f"Set {self.display_name} framerate to {framerate}Hz")
                self._updating = False
        except Exception as e:
            logger.error(f"Error setting framerate: {e}")
            self._updating = False


class DisplayModeSelector(Adw.ActionRow, Tweak):
    """Toggle buttons for selecting multiple display arrangement mode"""
    
    def __init__(self, **options):
        Adw.ActionRow.__init__(self)
        Tweak.__init__(
            self,
            title=_("Display Mode"),
            description=_("Configure how multiple displays are arranged"),
            **options
        )
        
        self.set_title(_("Display Mode"))
        self.set_subtitle(_("Extend or mirror displays"))
        
        self.display_mgr = get_display_manager()
        self.loaded = self.display_mgr is not None
        self._updating = False
        self._has_multiple_displays = False  # Will be set based on actual display count
        
        if not self.loaded:
            return
        
        # Check if we have multiple displays
        try:
            import os
            xdg_session = os.environ.get('XDG_SESSION_TYPE', '').lower()
            
            displays = self.display_mgr.get_displays()
            connected = [d['name'] for d in displays if d['connected']]
            self._has_multiple_displays = len(connected) > 1
            
            logger.debug(f"DisplayModeSelector: XDG_SESSION_TYPE={xdg_session}")
            logger.debug(f"DisplayModeSelector: Display manager available: {self.display_mgr.is_available()}")
            logger.debug(f"DisplayModeSelector: Found {len(displays)} total displays, {len(connected)} connected")
            
            if not self._has_multiple_displays:
                if len(connected) == 0 and xdg_session != 'wayland':
                    logger.warning(f"DisplayModeSelector: Not on Wayland (session: {xdg_session}), "
                                 f"display control requires Wayland")
                    self.set_sensitive(False)
                    self.set_subtitle(_("Requires Wayland session"))
                elif self.display_mgr.is_available() and len(connected) == 0:
                    logger.warning(f"DisplayModeSelector: Wayland detected but no displays found. "
                                 f"This may indicate a DBus or container issue.")
                    self.set_sensitive(False)
                    self.set_subtitle(_("No displays detected"))
                else:
                    logger.warning(f"DisplayModeSelector: Only {len(connected)} display(s) found, "
                                 f"display mode selection disabled")
                    self.set_sensitive(False)
                    self.set_subtitle(_("Multiple displays required"))
                return
        except Exception as e:
            logger.warning(f"DisplayModeSelector: Error checking displays at init: {type(e).__name__}: {e}")
            self.set_sensitive(False)
            self.set_subtitle(_("Unable to detect displays"))
            return
        
        # Create box for toggle buttons
        toggle_box = Gtk.Box(spacing=0)
        toggle_box.set_homogeneous(True)
        toggle_box.set_vexpand(False)
        toggle_box.set_valign(Gtk.Align.CENTER)
        toggle_box.add_css_class("linked")
        
        # Create Extend button
        self._extend_button = Gtk.ToggleButton.new_with_label(_("Extend"))
        self._extend_button.set_valign(Gtk.Align.CENTER)
        self._extend_button.set_vexpand(False)
        toggle_box.append(self._extend_button)
        
        # Create Mirror button
        self._mirror_button = Gtk.ToggleButton.new_with_label(_("Mirror"))
        self._mirror_button.set_valign(Gtk.Align.CENTER)
        self._mirror_button.set_vexpand(False)
        self._mirror_button.set_group(self._extend_button)
        toggle_box.append(self._mirror_button)
        
        # Set initial state to Extend (default)
        self._extend_button.set_active(True)
        
        # Connect signals
        self._extend_button.connect("toggled", self._on_mode_toggled)
        self._mirror_button.connect("toggled", self._on_mode_toggled)
        
        # Add to row
        self.add_suffix(toggle_box)
        self.set_activatable_widget(toggle_box)
        
        self.widget_for_size_group = None
    
    def _on_mode_toggled(self, button):
        """Handle mode toggle"""
        if self._updating or not button.get_active():
            return
        
        try:
            # Determine which mode was selected
            if button == self._extend_button:
                mode = DisplayMode.EXTEND
            else:
                mode = DisplayMode.MIRROR
            
            # Get all connected displays
            displays = self.display_mgr.get_displays()
            logger.debug(f"DisplayModeSelector: get_displays returned {len(displays)} displays")
            for d in displays:
                logger.debug(f"  Display: name={d['name']}, connected={d['connected']}")
            
            connected = [d['name'] for d in displays if d['connected']]
            logger.debug(f"DisplayModeSelector: Found {len(connected)} connected displays: {connected}")
            
            if len(connected) > 1:
                self._updating = True
                logger.info(f"Setting display mode to {mode.name}: {connected}")
                result = self.display_mgr.set_display_mode(connected, mode)
                logger.info(f"set_display_mode returned: {result}")
                self._updating = False
            else:
                logger.warning(f"Display mode selection requires multiple displays (have {len(connected)})")
                # Reset to previous state
                self._updating = True
                self._extend_button.set_active(not (button == self._extend_button))
                self._mirror_button.set_active(not (button == self._mirror_button))
                self._updating = False
        except Exception as e:
            logger.error(f"Error changing display mode: {e}", exc_info=True)
            self._updating = False


class FractionalScalingTweak(Adw.ActionRow, _GSettingsTweak, _DependableMixin):
    """Switch row for fractional scaling support (experimental)"""
    
    FEATURE_NAME = "scale-monitor-framebuffer"
    
    def __init__(self, **options):
        # We use a custom schema since experimental-features is a strv not a boolean
        _GSettingsTweak.__init__(
            self,
            title=_("Fractional Scaling (Experimental)"),
            schema_name="org.gnome.mutter",
            key_name="experimental-features",
            **options
        )
        
        Adw.ActionRow.__init__(
            self,
            title=_("Fractional Scaling (Experimental)"),
            subtitle=_("Enable experimental fractional scaling for better visual fidelity on high-DPI displays")
        )
        
        # Create switch widget
        switch = Gtk.Switch(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        
        # Manually handle state since we're dealing with a strv, not a boolean
        self._update_switch_from_settings(switch)
        
        # Connect to settings changes
        self.settings.connect("changed::experimental-features", self._on_settings_changed, switch)
        
        # Connect to switch changes
        switch.connect("notify::active", self._on_switch_changed)
        
        self.add_suffix(switch)
        self.set_activatable_widget(switch)
        self.widget_for_size_group = None
        
        # Store switch reference
        self._switch = switch
        
        self.add_dependency_on_tweak(
            options.get("depends_on"),
            options.get("depends_how")
        )
    
    def _update_switch_from_settings(self, switch):
        """Update switch state based on experimental-features strv"""
        try:
            features = self.settings.get_strv("experimental-features")
            is_enabled = self.FEATURE_NAME in features
            switch.set_active(is_enabled)
        except Exception as e:
            logger.error(f"Error reading experimental features: {e}")
            switch.set_active(False)
    
    def _on_settings_changed(self, settings, key, switch):
        """Handle external settings changes"""
        self._update_switch_from_settings(switch)
    
    def _on_switch_changed(self, switch, param):
        """Handle switch toggle"""
        try:
            features = list(self.settings.get_strv("experimental-features"))
            
            if switch.get_active():
                if self.FEATURE_NAME not in features:
                    features.append(self.FEATURE_NAME)
            else:
                if self.FEATURE_NAME in features:
                    features.remove(self.FEATURE_NAME)
            
            self.settings.set_strv("experimental-features", features)
        except Exception as e:
            logger.error(f"Error updating experimental features: {e}")
            # Reset on error
            self._update_switch_from_settings(switch)


class NightLightToggle(GSettingsTweakSwitchRow):
    """Toggle for Night Light feature"""
    
    def __init__(self, **options):
        GSettingsTweakSwitchRow.__init__(
            self,
            title=_("Night Light"),
            schema_name="org.gnome.settings-daemon.plugins.color",
            key_name="night-light-enabled",
            desc=_("Enable Night Light to reduce blue light emission in the evening"),
            **options
        )
        
        try:
            self.settings = Gio.Settings.new("org.gnome.settings-daemon.plugins.color")
            self.loaded = True
        except GLib.Error:
            self.loaded = False
            logger.debug("Night Light settings not available on this system")


class NightLightSchedule(Adw.ComboRow, Tweak):
    """Combo row for Night Light schedule mode (Sunset/Sunrise or Manual)"""
    
    def __init__(self, **options):
        Tweak.__init__(
            self,
            title=_("Night Light Schedule"),
            description=_("Set when Night Light should be active"),
            **options
        )
        
        self.loaded = False
        self.settings = None
        self._updating = False
        
        try:
            self.settings = Gio.Settings.new("org.gnome.settings-daemon.plugins.color")
            self.loaded = True
        except GLib.Error:
            logger.debug("Night Light settings not available")
            return
        
        # Create model with schedule options (value, display text)
        schedule_options = [
            (True, _("Sunset to Sunrise")),
            (False, _("Manual Schedule")),
        ]
        
        Adw.ComboRow.__init__(
            self,
            title=_("Night Light Schedule"),
            subtitle=_("Choose when Night Light is active")
        )
        
        # Set up factory for rendering BEFORE setting model
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._factory_setup)
        factory.connect("bind", self._factory_bind)
        self.set_factory(factory)
        
        # Build list store using the standard pattern
        self.set_model(build_list_store(schedule_options))
        
        # Set initial state
        self._update_from_settings()
        
        # Connect signals
        self.settings.connect("changed::night-light-schedule-automatic", self._on_settings_changed)
        self.connect("notify::selected-item", self._on_combo_changed)
        
        self.widget_for_size_group = self
    
    def _factory_setup(self, factory, item):
        """Set up list item factory"""
        label = Gtk.Label(xalign=0.0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=20, 
                          valign=Gtk.Align.CENTER)
        item.set_child(label)
    
    def _factory_bind(self, factory, item):
        """Bind data to list item"""
        label = item.get_child()
        label.set_label(item.get_item().title)
    
    def _update_from_settings(self):
        """Update combo selection from settings"""
        try:
            is_automatic = self.settings.get_boolean("night-light-schedule-automatic")
            model = self.get_model()
            
            # Find the matching item
            for i in range(len(model)):
                item = model.get_item(i)
                if item.value == is_automatic:
                    self.set_selected(i)
                    break
        except Exception as e:
            logger.debug(f"Could not update schedule from settings: {e}")
    
    def _on_combo_changed(self, combo, param):
        """Handle combo selection change"""
        if self._updating:
            return
        
        try:
            item = combo.get_selected_item()
            if item:
                self._updating = True
                self.settings.set_boolean("night-light-schedule-automatic", item.value)
                self._updating = False
        except Exception as e:
            logger.error(f"Could not update Night Light schedule: {e}")
    
    def _on_settings_changed(self, settings, key):
        """Handle external settings changes"""
        if not self._updating:
            self._update_from_settings()


class NightLightTemperature(Adw.ActionRow, Tweak):
    """Slider for adjusting Night Light color temperature"""
    
    def __init__(self, **options):
        Adw.ActionRow.__init__(self)
        Tweak.__init__(
            self,
            title=_("Color Temperature"),
            description=_("Adjust the warmth of Night Light effect"),
            **options
        )
        
        self.set_title(_("Color Temperature"))
        
        try:
            self.settings = Gio.Settings.new("org.gnome.settings-daemon.plugins.color")
            self.loaded = True
        except GLib.Error:
            self.loaded = False
            logger.debug("Night Light settings not available")
            return
        
        # Set subtitle explaining Kelvin scale
        self.set_subtitle(_("Warmer (1700K) to Cooler (5500K)"))
        
        # Temperature scale: 1700K (warmest/reddest) to 5500K (coolest/whitest)
        # Using 100K increments for reasonable control
        self.scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            1700.0,
            5500.0,
            100.0
        )
        self.scale.set_draw_value(True)
        self.scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.scale.set_hexpand(True)
        self.scale.set_size_request(200, -1)
        self.scale.set_valign(Gtk.Align.CENTER)
        
        # Add marks at preset color temperatures with labels
        self.scale.add_mark(1700.0, Gtk.PositionType.BOTTOM, _("Warm"))
        self.scale.add_mark(2700.0, Gtk.PositionType.BOTTOM, None)
        self.scale.add_mark(3500.0, Gtk.PositionType.BOTTOM, None)
        self.scale.add_mark(4700.0, Gtk.PositionType.BOTTOM, None)
        self.scale.add_mark(5500.0, Gtk.PositionType.BOTTOM, _("Cool"))
        
        # Define snap points for easier selection
        self._snap_points = [1700.0, 2700.0, 3500.0, 4700.0, 5500.0]
        self._snap_threshold = 75.0  # Snap if within 75K of a preset
        
        # Set initial value 
        try:
            temp_value = self.settings.get_uint("night-light-temperature")
            logger.debug(f"Current night-light-temperature from settings: {temp_value}")
            # Clamp to valid range
            temp_value = max(1700, min(5500, temp_value))
            self.scale.set_value(float(temp_value))
        except Exception as e:
            logger.debug(f"Could not get Night Light temperature: {e}")
            # Set a reasonable default (around 4000K, neutral)
            self.scale.set_value(4000.0)
        
        self.scale.connect("value-changed", self._on_temperature_changed)
        self.add_suffix(self.scale)
        
        # Listen for external changes
        self.settings.connect("changed::night-light-temperature", self._on_settings_changed)
        
        self._updating = False
    
    def _on_temperature_changed(self, scale):
        """Handle temperature slider change with snapping to presets"""
        if self._updating:
            return
        
        value = scale.get_value()
        
        # Check if value is within snap threshold of any preset
        for snap_point in self._snap_points:
            if abs(value - snap_point) < self._snap_threshold:
                # Snap to this preset
                value = snap_point
                self._updating = True
                scale.set_value(value)
                self._updating = False
                break
        
        value = int(value)
        try:
            self._updating = True
            logger.debug(f"Setting night-light-temperature to: {value}")
            # Use set_uint for unsigned integer
            self.settings.set_uint("night-light-temperature", value)
        except Exception as e:
            logger.error(f"Could not set Night Light temperature: {e}")
        finally:
            self._updating = False
    
    def _on_settings_changed(self, settings, key):
        """Handle external temperature changes"""
        if self._updating:
            return
            
        try:
            value = settings.get_uint(key)
            logger.debug(f"Night light temperature changed externally to: {value}")
            value = max(1700, min(5500, value))
            self.scale.set_value(float(value))
        except Exception as e:
            logger.debug(f"Could not update temperature slider: {e}")


class ScreenArrangementTweak(Adw.PreferencesGroup, Tweak):
    """Screen arrangement tweak for configuring multiple display positions"""
    
    def __init__(self, **options):
        Adw.PreferencesGroup.__init__(self, title=_("Screen Arrangement"))
        Tweak.__init__(
            self,
            title=_("Screen Arrangement"),
            description=_("Arrange and position your displays"),
            **options
        )
        
        self.display_mgr = get_display_manager()
        self.loaded = self.display_mgr is not None
        
        if not self.loaded:
            logger.warning("ScreenArrangementTweak: Display manager not available")
            # Add a label explaining that display configuration is not available
            label = Gtk.Label(label=_("Display configuration is not available in this environment"))
            label.add_css_class("dim-label")
            self.add(label)
            return
        
        # Check for multiple displays
        displays = self.display_mgr.get_displays()
        connected = [d for d in displays if d['connected']]
        
        if len(connected) < 2:
            label = Gtk.Label(label=_("Only one display detected. Display arrangement requires multiple displays."))
            label.add_css_class("dim-label")
            label.set_wrap(True)
            self.add(label)
            return
        
        # Create the screen arrangement widget
        self.arrangement_widget = ScreenArrangementWidget()
        self.arrangement_widget.set_displays(displays)
        self.arrangement_widget.connect("apply-arrangement", self._on_apply_arrangement)
        
        self.add(self.arrangement_widget)
        
        logger.debug(f"ScreenArrangementTweak: Initialized with {len(connected)} displays")
    
    def _on_apply_arrangement(self, widget, arrangement):
        """Handle apply arrangement button click"""
        try:
            logger.info(f"Applying display arrangement: {arrangement}")
            
            # Create a dialog to confirm
            parent = widget.get_root()
            if isinstance(parent, Gtk.Window):
                dialog = Gtk.AlertDialog.new()
                dialog.set_modal(True)
                dialog.set_message(_("Apply Display Configuration?"))
                dialog.set_detail(_("This will rearrange your displays. Cancel to revert if something goes wrong."))
                dialog.set_buttons(["Cancel", "Apply"])
                dialog.set_default_button(1)
                
                # Use async so we don't block
                dialog.choose(parent, None, self._on_confirmation_response, arrangement)
        except Exception as e:
            logger.error(f"Error applying arrangement: {e}", exc_info=True)
    
    def _on_confirmation_response(self, dialog, result, arrangement):
        """Handle confirmation dialog response"""
        try:
            response = dialog.choose_finish(result)
            if response == 1:  # Apply button
                success = self.display_mgr.apply_display_arrangement(arrangement)
                
                if success:
                    logger.info("Display arrangement applied successfully")
                    # Show success message
                    dialog = Gtk.AlertDialog.new()
                    dialog.set_modal(True)
                    dialog.set_message(_("Display Configuration Applied"))
                    dialog.set_detail(_("Your displays have been arranged as configured."))
                    dialog.add_response("ok", _("OK"))
                    dialog.set_default_response("ok")
                    dialog.present(self.get_root())
                else:
                    logger.error("Failed to apply display arrangement")
                    # Show error message
                    dialog = Gtk.AlertDialog.new()
                    dialog.set_modal(True)
                    dialog.set_message(_("Failed to Apply Configuration"))
                    dialog.set_detail(_("There was an error applying the display configuration."))
                    dialog.add_response("ok", _("OK"))
                    dialog.present(self.get_root())
        except Exception as e:
            logger.error(f"Error in confirmation response: {e}", exc_info=True)


# Build display tweaks
display_tweaks = []

# Advanced display settings - Display selector and primary controls
display_selector_tweak = DisplaySelectorRow()
primary_display_tweak = PrimaryDisplayToggle()
resolution_tweak = ResolutionSelector()
framerate_tweak = FramerateSelector()

# Connect display selector to update dependent controls
def on_display_selected(display_name):
    primary_display_tweak.set_display(display_name)
    resolution_tweak.set_display(display_name)
    framerate_tweak.set_display(display_name)

def on_resolution_selected(resolution):
    """Called when resolution is changed to update framerate selector"""
    if resolution:
        framerate_tweak.set_display(resolution_tweak.display_name, resolution)

if display_selector_tweak.loaded:
    display_selector_tweak.on_display_changed = on_display_selected
    resolution_tweak.on_resolution_changed = on_resolution_selected
    
    # Trigger initial setup for the currently selected display
    selected_display = display_selector_tweak.get_selected_display()
    if selected_display:
        on_display_selected(selected_display)

# Multiple display group - at the top
multi_display_tweaks = [
    DisplayModeSelector(),
]
if multi_display_tweaks[0].loaded:
    display_tweaks.append(TweakPreferencesGroup(_("Multiple Displays"), "multi-display", *multi_display_tweaks))

# Screen arrangement group
arrangement_tweak = ScreenArrangementTweak()
if arrangement_tweak.loaded:
    display_tweaks.append(arrangement_tweak)

# Combined primary display and resolution group
primary_group_tweaks = [
    display_selector_tweak,
    primary_display_tweak,
    resolution_tweak,
    framerate_tweak,
]
if display_selector_tweak.loaded:
    display_tweaks.append(TweakPreferencesGroup(_("Primary Display"), "primary-display", *primary_group_tweaks))

# Scaling group
scaling_tweaks = [
    FractionalScalingTweak(),
]
display_tweaks.append(TweakPreferencesGroup(_("Scaling"), "scaling", *scaling_tweaks))

# Night Light group
night_light_tweaks = [
    NightLightToggle(),
    NightLightSchedule(),
    NightLightTemperature(),
]
display_tweaks.append(TweakPreferencesGroup(_("Night Light"), "nightlight", *night_light_tweaks))

TWEAK_GROUP = TweakPreferencesPage(
    "display",
    _("Display"),
    *display_tweaks,
)
