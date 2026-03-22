# Copyright (c) 2011 John Stowers
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import os
import os.path
import configparser
import logging

from gi.repository import Gtk, Adw, GLib, Gio

from gtweak.utils import get_resource_dirs
from gtweak.widgets import (TweakPreferencesPage, TweakPreferencesGroup, GSettingsTweakComboRow, 
                            GSettingsTweakSwitchRow, _GSettingsTweak, Tweak)
from gtweak.audio.audio_manager import get_audio_manager, HAS_PIPEWIRE

logger = logging.getLogger(__name__)


def get_theme_name(index_path):
    """Given an index file path, gets the relevant sound theme's name."""
    config = configparser.ConfigParser()
    config.read(index_path)
    return config["Sound Theme"]["Name"]


def get_sound_themes():
    """Gets the available sound themes as a (theme_directory_name, theme_display_name) tuple list."""
    themes = []
    seen = set()
    for location in get_resource_dirs("sounds"):
        for item in os.listdir(location):
            candidate = os.path.join(location, item)
            index_file = os.path.join(candidate, "index.theme")
            if os.path.isdir(candidate) and os.path.exists(index_file):
                theme_info = (os.path.basename(candidate), get_theme_name(index_file))
                if theme_info[1] not in seen:
                    themes.append(theme_info)
                    seen.add(theme_info[1])
    return themes


class OutputDeviceSelector(Adw.ActionRow, Tweak):
    """Widget for selecting the default audio output device"""
    
    def __init__(self, **options):
        logger.debug("OutputDeviceSelector.__init__() called")
        Adw.ActionRow.__init__(self)
        Tweak.__init__(self, title="Output Device", description="", **options)
        
        self.set_title("Output Device")
        
        # Required by tweaks framework
        self.loaded = True
        self.widget_for_size_group = None
        
        self.pa_manager = get_audio_manager()
        logger.debug(f"  pa_manager type: {type(self.pa_manager).__name__ if self.pa_manager else 'None'}")
        
        # Create combo box model with icon support
        store = Gtk.ListStore(str, str, str)  # id, display_text, icon_name
        self.combo_box = Gtk.ComboBox(model=store)
        self.combo_box.set_hexpand(True)
        self.combo_box.set_size_request(300, -1)
        
        # Create icon renderer
        icon_renderer = Gtk.CellRendererPixbuf()
        self.combo_box.pack_start(icon_renderer, False)
        self.combo_box.add_attribute(icon_renderer, "icon-name", 2)
        
        # Create text renderer
        text_renderer = Gtk.CellRendererText()
        self.combo_box.pack_start(text_renderer, True)
        self.combo_box.add_attribute(text_renderer, "text", 1)
        
        if not self.pa_manager or not self.pa_manager.is_available():
            logger.warning(f"  OutputDeviceSelector: manager unavailable")
            no_dev_iter = store.append(["", "No audio devices available", "dialog-error"])
            self.combo_box.set_active_iter(no_dev_iter)
            self.combo_box.set_sensitive(False)
            self.add_suffix(self.combo_box)
            return
        
        # Build combo box with available devices
        logger.debug("  Building OutputDeviceSelector combo box...")
        
        try:
            sinks = self.pa_manager.get_sinks()
            logger.debug(f"  get_sinks() returned {len(sinks)} devices")
            
            if not sinks or len(sinks) == 0:
                logger.warning("  No sinks available")
                store.append(["", "No devices found", "dialog-error"])
                self.combo_box.set_active(0)
                self.combo_box.set_sensitive(False)
            else:
                default_sink = self.pa_manager.get_default_sink()
                logger.debug(f"  default_sink: {default_sink}")
                active_idx = None
                
                for idx, (sink_name, sink_desc, icon_name) in enumerate(sinks):
                    logger.debug(f"    [{idx}] {sink_desc} (ID: {sink_name}, icon: {icon_name})")
                    store.append([sink_name, sink_desc, icon_name])
                    if sink_name == default_sink:
                        active_idx = idx
                
                if store.iter_n_children(None) > 0 and active_idx is not None:
                    self.combo_box.set_active(active_idx)
                    self.combo_box.connect("changed", self._on_device_changed)
                elif store.iter_n_children(None) > 0:
                    self.combo_box.set_active(0)
                    self.combo_box.connect("changed", self._on_device_changed)
                else:
                    store.append(["", "No valid devices", "dialog-error"])
                    self.combo_box.set_active(0)
                    self.combo_box.set_sensitive(False)
        except Exception as e:
            logger.error(f"  Error building combo box: {e}", exc_info=True)
            store.append(["", "Error loading devices", "dialog-error"])
            self.combo_box.set_active(0)
            self.combo_box.set_sensitive(False)
        
        self.add_suffix(self.combo_box)
        self.set_activatable_widget(self.combo_box)
    
    def _on_device_changed(self, combo):
        """Handle device selection change"""
        if not self.pa_manager or not self.pa_manager.is_available():
            return
        
        iter_obj = combo.get_active_iter()
        if iter_obj:
            device_name = combo.get_model()[iter_obj][0]
            if device_name:
                self.pa_manager.set_default_sink(device_name)
                logger.info(f"Changed output device to: {device_name}")


class InputDeviceSelector(Adw.ActionRow, Tweak):
    """Widget for selecting the default audio input device"""
    
    def __init__(self, **options):
        logger.debug("InputDeviceSelector.__init__() called")
        Adw.ActionRow.__init__(self)
        Tweak.__init__(self, title="Input Device", description="", **options)
        
        self.set_title("Input Device")
        
        # Required by tweaks framework
        self.loaded = True
        self.widget_for_size_group = None
        
        self.pa_manager = get_audio_manager()
        logger.debug(f"  pa_manager type: {type(self.pa_manager).__name__ if self.pa_manager else 'None'}")
        
        # Create model with: device_id (str), display_text (str), icon_name (str)
        store = Gtk.ListStore(str, str, str)
        self.combo_box = Gtk.ComboBox(model=store)
        self.combo_box.set_hexpand(True)
        self.combo_box.set_size_request(300, -1)
        
        # Create cell renderers
        icon_renderer = Gtk.CellRendererPixbuf()
        text_renderer = Gtk.CellRendererText()
        
        # Pack renderers
        self.combo_box.pack_start(icon_renderer, False)
        self.combo_box.pack_start(text_renderer, True)
        
        # Add attributes
        self.combo_box.add_attribute(icon_renderer, "icon-name", 2)
        self.combo_box.add_attribute(text_renderer, "text", 1)
        
        if not self.pa_manager or not self.pa_manager.is_available():
            logger.warning(f"  InputDeviceSelector: manager unavailable")
            store.append(["no-device", "No audio devices available", "audio-input-microphone"])
            self.combo_box.set_active(0)
            self.combo_box.set_sensitive(False)
            self.add_suffix(self.combo_box)
            return
        
        # Build combo box with available devices
        logger.debug("  Building InputDeviceSelector combo box...")
        
        try:
            sources = self.pa_manager.get_sources()
            logger.debug(f"  get_sources() returned {len(sources)} devices")
            
            if not sources or len(sources) == 0:
                logger.warning("  No sources available")
                store.append(["no-device", "No devices found", "audio-input-microphone"])
                self.combo_box.set_active(0)
                self.combo_box.set_sensitive(False)
            else:
                default_source = self.pa_manager.get_default_source()
                logger.debug(f"  default_source: {default_source}")
                active_idx = 0
                
                for idx, (source_name, source_desc, icon_name) in enumerate(sources):
                    # source_name is the device ID, source_desc is the human-readable description
                    logger.debug(f"    [{idx}] {source_desc} (ID: {source_name}, icon: {icon_name})")
                    store.append([source_name, source_desc, icon_name])
                    if source_name == default_source:
                        active_idx = idx
                
                if len(store) > 0:
                    self.combo_box.set_active(active_idx)
                    self.combo_box.connect("changed", self._on_device_changed)
                else:
                    store.append(["no-device", "No valid devices", "audio-input-microphone"])
                    self.combo_box.set_active(0)
                    self.combo_box.set_sensitive(False)
        except Exception as e:
            logger.error(f"  Error building combo box: {e}", exc_info=True)
            store.append(["error", "Error loading devices", "audio-input-microphone"])
            self.combo_box.set_active(0)
            self.combo_box.set_sensitive(False)
        
        self.add_suffix(self.combo_box)
        self.set_activatable_widget(self.combo_box)
    
    def _on_device_changed(self, combo):
        """Handle device selection change"""
        if not self.pa_manager or not self.pa_manager.is_available():
            return
        
        iter_obj = combo.get_active_iter()
        if iter_obj:
            device_name = combo.get_model()[iter_obj][0]
            if device_name:
                self.pa_manager.set_default_source(device_name)
                logger.info(f"Changed input device to: {device_name}")


class VolumeControl(Adw.ActionRow, Tweak):
    """Widget for controlling audio volume"""
    
    def __init__(self, device_type="sink", **options):
        logger.debug(f"VolumeControl.__init__() called (device_type={device_type})")
        Adw.ActionRow.__init__(self)
        
        self.device_type = device_type  # "sink" or "source"
        self.pa_manager = get_audio_manager()
        logger.debug(f"  pa_manager type: {type(self.pa_manager).__name__ if self.pa_manager else 'None'}")
        
        title = "Output Volume" if device_type == "sink" else "Input Volume"
        
        Tweak.__init__(self, title=title, description="", **options)
        
        self.set_title(title)
        
        # Required by tweaks framework
        self.loaded = True
        self.widget_for_size_group = None
        self._updating = False
        self._initializing = True  # Flag to prevent slider changes during init
        
        # Store sound settings for listening to changes
        try:
            self.sound_settings = Gio.Settings.new("org.gnome.desktop.sound")
            self.sound_settings.connect("changed::allow-volume-above-100-percent", self._on_volume_limit_changed)
        except Exception as e:
            logger.debug(f"Could not connect to sound settings: {e}")
            self.sound_settings = None
        
        if not self.pa_manager or not self.pa_manager.is_available():
            logger.warning(f"  VolumeControl({device_type}): manager unavailable")
            label_unavail = Gtk.Label(label="Not available")
            label_unavail.add_css_class("dim-label")
            self.add_suffix(label_unavail)
            return
        
        # Check if volume above 100% is allowed (only for output devices)
        allow_above_100 = False
        try:
            if self.sound_settings and device_type == "sink":  # Only for output
                allow_above_100 = self.sound_settings.get_boolean("allow-volume-above-100-percent")
        except Exception as e:
            logger.debug(f"Could not read volume limit setting: {e}")
        
        max_volume = 1.59 if allow_above_100 else 1.0
        
        # Volume slider
        self.volume_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, max_volume, 0.01
        )
        self.volume_scale.set_hexpand(True)
        self.volume_scale.set_draw_value(False)
        self.volume_scale.set_size_request(200, -1)
        
        # Add mark at 100% if we allow above 100%
        if max_volume > 1.0:
            self.volume_scale.add_mark(1.0, Gtk.PositionType.BOTTOM, "100%")
        
        # Get current volume - set initial value BEFORE connecting signal
        current_vol = 1.0
        try:
            if device_type == "sink":
                # Use @DEFAULT_AUDIO_SINK@ alias to always control the current default
                vol = self.pa_manager.get_sink_volume("@DEFAULT_AUDIO_SINK@")
                if vol is not None:
                    current_vol = vol
                    logger.debug(f"  current output volume: {current_vol}")
            else:
                # Use @DEFAULT_AUDIO_SOURCE@ alias to always control the current default
                vol = self.pa_manager.get_source_volume("@DEFAULT_AUDIO_SOURCE@")
                if vol is not None:
                    current_vol = vol
                    logger.debug(f"  current input volume: {current_vol}")
        except Exception as e:
            logger.error(f"Error getting initial volume: {e}")
        
        # Set initial value without triggering change signal
        self.volume_scale.set_value(current_vol)
        
        # NOW connect the change signal (after setting initial value)
        self.volume_scale.connect("value-changed", self._on_volume_changed)
        self._initializing = False  # Done initializing
        
        self.add_suffix(self.volume_scale)
    
    def _on_volume_limit_changed(self, settings, key):
        """Handle change to allow-volume-above-100-percent setting"""
        try:
            allow_above_100 = settings.get_boolean(key)
            # Only apply above-100% to output devices (sinks)
            max_volume = 1.59 if (allow_above_100 and self.device_type == "sink") else 1.0
            
            # Update the slider's adjustment
            adjustment = self.volume_scale.get_adjustment()
            adjustment.set_upper(max_volume)
            
            # If limiting to 100% and current volume is above 100%, clamp it
            if not allow_above_100 and self.device_type == "sink":
                current_volume = self.volume_scale.get_value()
                if current_volume > 1.0:
                    logger.debug(f"Clamping volume from {current_volume} to 1.0")
                    self._updating = True  # Prevent triggering volume change handler
                    try:
                        # Set the slider and the actual device volume to 1.0
                        self.volume_scale.set_value(1.0)
                        if self.pa_manager and self.pa_manager.is_available():
                            self.pa_manager.set_sink_volume("@DEFAULT_AUDIO_SINK@", 1.0)
                            logger.info("Clamped output volume to 100%")
                    finally:
                        self._updating = False
            
            # Remove old marks and add new one if needed
            self.volume_scale.clear_marks()
            if max_volume > 1.0:
                self.volume_scale.add_mark(1.0, Gtk.PositionType.BOTTOM, "100%")
            
            logger.debug(f"Updated volume slider max to: {max_volume}")
        except Exception as e:
            logger.error(f"Error updating volume limit: {e}", exc_info=True)
    
    def _on_volume_changed(self, scale):
        """Handle volume slider change"""
        if self._initializing or self._updating:
            return
        
        if not self.pa_manager or not self.pa_manager.is_available():
            logger.warning("_on_volume_changed: manager not available")
            return
        
        self._updating = True
        try:
            volume = scale.get_value()
            logger.debug(f"Volume changed to: {volume} (device_type={self.device_type})")
            
            if self.device_type == "sink":
                # Use @DEFAULT_AUDIO_SINK@ alias to always control the current default
                success = self.pa_manager.set_sink_volume("@DEFAULT_AUDIO_SINK@", volume)
                if success:
                    logger.info(f"Set output volume to: {volume}")
                else:
                    logger.warning(f"Failed to set output volume")
            else:
                # Use @DEFAULT_AUDIO_SOURCE@ alias to always control the current default
                success = self.pa_manager.set_source_volume("@DEFAULT_AUDIO_SOURCE@", volume)
                if success:
                    logger.info(f"Set input volume to: {volume}")
                else:
                    logger.warning(f"Failed to set input volume")
        finally:
            self._updating = False


sound_themes = get_sound_themes()

# Build sound tweaks with organized groups
sound_tweaks = []

# General sound settings group
general_tweaks = [
    GSettingsTweakSwitchRow(
        "Event Sounds",
        "org.gnome.desktop.sound",
        "event-sounds",
        desc="Play a sound when an event occurs.",
    )
]

# Audio devices and volume controls if available
if HAS_PIPEWIRE:
    try:
        pa_manager = get_audio_manager()
        
        if pa_manager:
            is_avail = pa_manager.is_available()
            
            if is_avail:
                # Output group: device selector + volume control
                output_tweaks = []
                
                output_tweaks.append(OutputDeviceSelector())
                
                output_tweaks.append(VolumeControl(device_type="sink"))

                output_tweaks.append(GSettingsTweakSwitchRow(
                    "Allow Volume Above 100%",
                    "org.gnome.desktop.sound",
                    "allow-volume-above-100-percent",
                    desc="Allow the system volume to be set above 100%, with the tradeoff of reduced sound quality.",
                ))
                
                sound_tweaks.append(TweakPreferencesGroup("Output", "output", *output_tweaks))
                
                # Input group: device selector + volume control
                input_tweaks = []
                
                input_tweaks.append(InputDeviceSelector())
                
                input_tweaks.append(VolumeControl(device_type="source"))
                
                sound_tweaks.append(TweakPreferencesGroup("Input", "input", *input_tweaks))
                

                
                pa_manager.close()
            else:
                logger.warning("Audio manager not available")
        else:
            logger.warning("get_audio_manager() returned None")
    except Exception as e:
        logger.warning(f"Failed to load audio controls: {e}", exc_info=True)

show_sound_tweaks = len(sound_tweaks) > 0

# Add sound theme selector if themes are available
if len(sound_themes) > 0:
    general_tweaks.append(
        GSettingsTweakComboRow(
            "System Sound Theme",
            "org.gnome.desktop.sound",
            "theme-name",
            sound_themes,
            desc="Specifies which sound theme to use for sound events.",
        )
    )

sound_tweaks.append(TweakPreferencesGroup("Sounds", "general", *general_tweaks))

TWEAK_GROUP = TweakPreferencesPage(
    "sound",
    "Sound",
    *sound_tweaks,
)





