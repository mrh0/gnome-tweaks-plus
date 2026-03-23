# Copyright (c) 2026 MRH0
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

"""
Advanced display configuration tweaks using display_manager.
Provides UI for: primary display, resolution, framerate, display modes, and HDR.
"""

import logging
from typing import List, Optional
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, Pango

from gtweak.tweakmodel import Tweak, TweakGroup
from gtweak.widgets import (
    TweakPreferencesPage,
    TweakPreferencesGroup,
    build_list_store,
    TweakListStoreItem,
)
from gtweak.display.display_manager import (
    get_display_manager,
    DisplayMode,
    XRandrDisplayManager
)

logger = logging.getLogger(__name__)

# Set up translation function
try:
    _
except NameError:
    def _(msg):
        return msg


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
        
        self.set_model(model)
        
        # Set up factory
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._factory_setup)
        factory.connect("bind", self._factory_bind)
        self.set_factory(factory)
        
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
    
    def __init__(self, display_name: Optional[str] = None, **options):
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
        self.display_name = display_name
        self.loaded = self.display_mgr is not None
        self._updating = False
        
        if self.loaded:
            self._refresh_resolutions()
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
            
            self.set_model(model)
            
            # Set up factory
            factory = Gtk.SignalListItemFactory()
            factory.connect("setup", self._factory_setup)
            factory.connect("bind", self._factory_bind)
            self.set_factory(factory)
            
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
                return
            
            # Use current resolution or first available
            res = self.current_resolution or display['resolution']
            
            # Find framerates for this resolution
            framerates = []
            for mode in display['modes']:
                if mode['resolution'] == res:
                    framerates = sorted(mode['framerates'], reverse=True)
                    break
            
            if not framerates:
                logger.warning(f"No framerates found for {self.display_name} at {res}")
                return
            
            model = build_list_store([
                (str(fr), f"{fr:.2f} Hz")
                for fr in framerates
            ])
            
            self.set_model(model)
            
            # Set up factory
            factory = Gtk.SignalListItemFactory()
            factory.connect("setup", self._factory_setup)
            factory.connect("bind", self._factory_bind)
            self.set_factory(factory)
            
            # Set current framerate
            if display['framerate']:
                for i, fr in enumerate(framerates):
                    if abs(fr - display['framerate']) < 0.1:  # Allow small floating point diff
                        self.set_selected(i)
                        break
        
        except Exception as e:
            logger.error(f"Error refreshing framerates: {e}")
    
    def _factory_setup(self, factory, item):
        """Set up list item factory"""
        label = Gtk.Label(xalign=0.0)
        item.set_child(label)
    
    def _factory_bind(self, factory, item):
        """Bind data to list item"""
        label = item.get_child()
        label.set_label(item.get_item().subtitle)
    
    def _on_framerate_changed(self, combo, param):
        """Handle framerate selection change"""
        if self._updating or not self.display_name or not self.current_resolution:
            return
        
        try:
            item = combo.get_selected_item()
            if item:
                framerate = float(item.title)
                width, height = map(int, self.current_resolution.split('x'))
                
                self._updating = True
                if self.display_mgr.set_framerate(self.display_name, width, height, framerate):
                    logger.info(f"Set {self.display_name} framerate to {framerate}Hz")
                self._updating = False
        except Exception as e:
            logger.error(f"Error setting framerate: {e}")
            self._updating = False


class DisplayModeSelector(Adw.ComboRow, Tweak):
    """Combo row for selecting multiple display arrangement mode"""
    
    def __init__(self, **options):
        Tweak.__init__(
            self,
            title=_("Display Mode"),
            description=_("Configure how multiple displays are arranged"),
            **options
        )
        
        Adw.ComboRow.__init__(
            self,
            title=_("Display Mode"),
            subtitle=_("Extend or mirror displays")
        )
        
        self.display_mgr = get_display_manager()
        self.loaded = self.display_mgr is not None
        
        if not self.loaded:
            return
        
        # Build list of display mode options
        mode_options = [
            (str(DisplayMode.EXTEND), _("Extend (Side by Side)")),
            (str(DisplayMode.MIRROR), _("Mirror (Same Image)")),
        ]
        
        model = build_list_store(mode_options)
        self.set_model(model)
        
        # Set up factory
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._factory_setup)
        factory.connect("bind", self._factory_bind)
        self.set_factory(factory)
        
        # Set default
        self.set_selected(0)  # Extend by default
        
        self.connect("notify::selected-item", self._on_mode_changed)
        self.widget_for_size_group = None
    
    def _factory_setup(self, factory, item):
        """Set up list item factory"""
        label = Gtk.Label(xalign=0.0)
        item.set_child(label)
    
    def _factory_bind(self, factory, item):
        """Bind data to list item"""
        label = item.get_child()
        label.set_label(item.get_item().subtitle)
    
    def _on_mode_changed(self, combo, param):
        """Handle display mode change"""
        item = combo.get_selected_item()
        if item:
            try:
                mode = DisplayMode(int(item.title))
                
                # Get all connected displays
                displays = self.display_mgr.get_displays()
                connected = [d['name'] for d in displays if d['connected']]
                
                if len(connected) > 1:
                    logger.info(f"Setting display mode to {mode.name}")
                    self.display_mgr.set_display_mode(connected, mode)
                else:
                    logger.warning("Display mode selection requires multiple displays")
            except Exception as e:
                logger.error(f"Error changing display mode: {e}")


# Build display tweaks - organized into sections
def _build_display_tweaks():
    """Factory function to lazily build display tweaks"""
    display_tweaks = []
    
    # Display selector and primary display group
    display_selector_tweak = DisplaySelectorRow()
    primary_display_tweak = PrimaryDisplayToggle()
    resolution_tweak = ResolutionSelector()
    framerate_tweak = FramerateSelector()
    
    # Connect display selector to update dependent controls
    def on_display_selected(display_name):
        primary_display_tweak.set_display(display_name)
        resolution_tweak.set_display(display_name)
        framerate_tweak.set_display(display_name)
    
    display_selector_tweak.on_display_changed = on_display_selected
    
    # Primary display group
    primary_group_tweaks = [
        display_selector_tweak,
        primary_display_tweak,
    ]
    display_tweaks.append(TweakPreferencesGroup(_("Primary Display"), "primary-display", *primary_group_tweaks))
    
    # Resolution and framerate group
    resolution_group_tweaks = [
        resolution_tweak,
        framerate_tweak,
    ]
    display_tweaks.append(TweakPreferencesGroup(_("Resolution and Refresh Rate"), "resolution", *resolution_group_tweaks))
    
    # Multiple display group
    multi_display_tweaks = [
        DisplayModeSelector(),
    ]
    display_tweaks.append(TweakPreferencesGroup(_("Multiple Displays"), "multi-display", *multi_display_tweaks))
    
    # Create the preferences page
    return TweakPreferencesPage(
        "display-advanced",
        _("Display Config"),
        *display_tweaks,
    )


# Create the preferences page (lazy initialization)
TWEAK_GROUP = _build_display_tweaks()
