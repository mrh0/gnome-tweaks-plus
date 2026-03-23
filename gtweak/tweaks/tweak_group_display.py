# Copyright (c) 2011 John Stowers
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import logging
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

logger = logging.getLogger(__name__)

# Set up translation function
try:
    # Try to use the system-wide gettext if available
    _
except NameError:
    # Fallback: define a simple translation function
    def _(msg):
        return msg


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
        
        # Build list store using the standard pattern
        self.set_model(build_list_store(schedule_options))
        
        # Set up factory for rendering
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._factory_setup)
        factory.connect("bind", self._factory_bind)
        self.set_factory(factory)
        
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
        """Handle temperature slider change"""
        if self._updating:
            return
        
        value = int(scale.get_value())
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


# Build display tweaks
display_tweaks = []

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
