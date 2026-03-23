# Copyright (c) 2011 John Stowers
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import logging
import builtins
from gi.repository import Gtk, Adw, Gio, GLib, GObject
from gtweak.tweakmodel import Tweak, TweakGroup
from gtweak.widgets import TweakPreferencesPage, TweakPreferencesGroup, GSettingsTweakSwitchRow
from gtweak.gsettings import GSettingsSetting

LOG = logging.getLogger(__name__)

# Ensure translation function is available globally
if not hasattr(builtins, '_'):
    builtins._ = lambda msg: msg

_ = builtins._


class BatteryStatusRow(Adw.ActionRow, Tweak):
    """Widget displaying current battery status and charge percentage"""

    def __init__(self, **options):
        Adw.ActionRow.__init__(self)
        Tweak.__init__(
            self,
            title=_("Battery Status"),
            description=_("Current battery charge level"),
            uid="battery_status",
            **options
        )

        self.set_title(_("Battery Status"))
        self._battery_label = Gtk.Label()
        self._battery_label.add_css_class("monospace")
        self.add_suffix(self._battery_label)
        
        self._upower_proxy = None
        self._battery_device = None
        
        try:
            self._init_upower()
        except Exception as e:
            LOG.warning(f"Failed to initialize UPower: {e}")
            self.loaded = False

    def _init_upower(self):
        """Initialize UPower D-Bus proxy"""
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            self._upower_proxy = Gio.DBusProxy.new_sync(
                bus, 0, None,
                'org.freedesktop.UPower',
                '/org/freedesktop/UPower',
                'org.freedesktop.UPower',
                None
            )
            
            # Find the battery device
            self._find_battery_device()
            
            # Update battery status periodically
            GLib.timeout_add_seconds(5, self._update_battery_status)
            self._update_battery_status()
        except Exception as e:
            LOG.warning(f"UPower initialization failed: {e}")

    def _find_battery_device(self):
        """Find the primary battery device"""
        try:
            devices = self._upower_proxy.EnumerateDevices()
            for device_path in devices:
                device_proxy = Gio.DBusProxy.new_sync(
                    Gio.bus_get_sync(Gio.BusType.SYSTEM, None), 0, None,
                    'org.freedesktop.UPower',
                    device_path,
                    'org.freedesktop.UPower.Device',
                    None
                )
                # Type 2 = battery
                device_type = device_proxy.get_cached_property('Type')
                if device_type and device_type.unpack() == 2:
                    self._battery_device = device_proxy
                    break
        except Exception as e:
            LOG.warning(f"Failed to find battery device: {e}")

    def _update_battery_status(self):
        """Update the displayed battery status"""
        if not self._battery_device:
            self._battery_label.set_label(_("No battery found"))
            return True

        try:
            percentage = self._battery_device.get_cached_property('Percentage')
            state = self._battery_device.get_cached_property('State')
            
            if percentage:
                pct = percentage.unpack()
                state_name = self._get_battery_state_name(state.unpack() if state else 0)
                self._battery_label.set_label(f"{pct:.0f}% ({state_name})")
            else:
                self._battery_label.set_label(_("Unknown"))
        except Exception as e:
            LOG.error(f"Failed to update battery status: {e}")
        
        return True

    @staticmethod
    def _get_battery_state_name(state):
        """Convert battery state enum to readable name"""
        state_names = {
            0: _("Unknown"),
            1: _("Charging"),
            2: _("Discharging"),
            3: _("Empty"),
            4: _("Fully Charged"),
            5: _("Pending Charge"),
            6: _("Pending Discharge"),
        }
        return state_names.get(state, _("Unknown"))


class PowerModeRow(Adw.ComboRow, Tweak):
    """Widget for selecting power profile"""

    def __init__(self, **options):
        Adw.ComboRow.__init__(self)
        Tweak.__init__(
            self,
            title=_("Power Mode"),
            description=_("Select power saving mode"),
            uid="power_mode",
            **options
        )

        self.set_title(_("Power Mode"))
        self.set_subtitle(_("Adjust performance vs. battery life"))
        
        self._profiles_proxy = None
        self._active_profile = None
        self._profile_ids = []
        
        try:
            self._init_power_profiles()
        except Exception as e:
            LOG.warning(f"Failed to initialize Power Profiles Daemon: {e}")
            self.loaded = False

    def _init_power_profiles(self):
        """Initialize Power Profiles Daemon D-Bus proxy"""
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            self._profiles_proxy = Gio.DBusProxy.new_sync(
                bus, 0, None,
                'net.hadess.PowerProfiles',
                '/net/hadess/PowerProfiles',
                'net.hadess.PowerProfiles',
                None
            )
            
            # Get available profiles
            profiles_prop = self._profiles_proxy.get_cached_property('Profiles')
            active_prop = self._profiles_proxy.get_cached_property('ActiveProfile')
            
            if profiles_prop:
                try:
                    profiles_list = profiles_prop.unpack()
                    if not isinstance(profiles_list, (list, tuple)):
                        LOG.warning(f"Profiles property is not a list: {type(profiles_list)}")
                        return
                    
                    model = Gtk.StringList()
                    
                    profile_names = {
                        'power-saver': _("Power Saver"),
                        'balanced': _("Balanced"),
                        'performance': _("Performance"),
                    }
                    
                    # Store profile IDs for later reference
                    self._profile_ids = []
                    
                    for profile in profiles_list:
                        # Extract profile name from variant or string
                        if isinstance(profile, str):
                            profile_id = profile
                        else:
                            # Handle variant objects from D-Bus
                            try:
                                profile_dict = profile.unpack() if hasattr(profile, 'unpack') else profile
                                profile_id = profile_dict.get('Profile', str(profile_dict)) if isinstance(profile_dict, dict) else str(profile)
                            except:
                                profile_id = str(profile)
                        
                        self._profile_ids.append(profile_id)
                        display_name = profile_names.get(profile_id, profile_id.replace('-', ' ').title())
                        model.append(display_name)
                    
                    self.set_model(model)
                    
                    # Set active profile
                    if active_prop:
                        active_profile = active_prop.unpack()
                        if isinstance(active_profile, str):
                            try:
                                index = self._profile_ids.index(active_profile)
                                self.set_selected(index)
                                self._active_profile = active_profile
                            except ValueError:
                                LOG.warning(f"Active profile {active_profile} not in profiles list")
                except Exception as e:
                    LOG.warning(f"Failed to process power profiles: {e}")
            
            # Connect signal for profile changes
            self.connect("notify::selected", self._on_profile_changed)
        except Exception as e:
            LOG.warning(f"Power Profiles initialization failed: {e}")

    def _on_profile_changed(self, widget, pspec):
        """Handle power profile selection change"""
        try:
            if not self._profiles_proxy or not hasattr(self, '_profile_ids'):
                return
                
            selected_index = self.get_selected()
            
            if 0 <= selected_index < len(self._profile_ids):
                profile_id = self._profile_ids[selected_index]
                # Use DBus Properties.Set to change the ActiveProfile property
                self._profiles_proxy.call_sync(
                    'org.freedesktop.DBus.Properties.Set',
                    GLib.Variant('(ssv)', 
                        ('net.hadess.PowerProfiles', 'ActiveProfile', 
                         GLib.Variant('s', profile_id))),
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None
                )
                LOG.debug(f"Power profile changed to: {profile_id}")
        except Exception as e:
            LOG.error(f"Failed to change power profile: {e}")


class IdleDimTweak(GSettingsTweakSwitchRow):
    """Toggle screen dimming when idle"""
    def __init__(self, **options):
        try:
            GSettingsTweakSwitchRow.__init__(
                self,
                _("Dim Screen When Idle"),
                "org.gnome.settings-daemon.plugins.power",
                "idle-dim",
                desc=_("Automatically dim screen after a period of inactivity"),
                **options
            )
        except Exception as e:
            LOG.warning(f"Failed to create idle dim tweak: {e}")
            self.loaded = False


class SleepTimeoutBatteryTweak(Adw.ActionRow, Tweak):
    """Control for setting battery sleep timeout duration"""
    
    def __init__(self, **options):
        Adw.ActionRow.__init__(self)
        Tweak.__init__(
            self,
            title=_("Sleep Timeout (Battery)"),
            description=_("Minutes before sleep on battery"),
            uid="sleep_timeout_battery",
            **options
        )
        
        self.set_title(_("Sleep Timeout (Battery)"))
        self.set_subtitle(_("Minutes before sleep"))
        
        self._settings = GSettingsSetting("org.gnome.settings-daemon.plugins.power")
        self._updating = False
        
        battery_adjustment = Gtk.Adjustment(
            value=10,
            lower=1,
            upper=120,
            step_increment=1,
            page_increment=10
        )
        battery_spin = Gtk.SpinButton(adjustment=battery_adjustment)
        battery_spin.set_numeric(True)
        
        current_battery_timeout = self._settings.get_int("sleep-inactive-battery-timeout")
        battery_spin.set_value(current_battery_timeout / 60)
        battery_spin.connect("value-changed", self._on_timeout_changed)
        self._spin = battery_spin
        
        self.add_suffix(battery_spin)

    def _on_timeout_changed(self, spin_button):
        """Handle battery sleep timeout change"""
        if self._updating:
            return
        
        self._updating = True
        try:
            minutes = int(spin_button.get_value())
            seconds = minutes * 60
            self._settings.set_int("sleep-inactive-battery-timeout", seconds)
            LOG.debug(f"Battery sleep timeout set to {minutes} minutes")
        except Exception as e:
            LOG.error(f"Failed to set battery sleep timeout: {e}")
        finally:
            self._updating = False


class SleepTimeoutACTweak(Adw.ActionRow, Tweak):
    """Control for setting AC sleep timeout duration"""
    
    def __init__(self, **options):
        Adw.ActionRow.__init__(self)
        Tweak.__init__(
            self,
            title=_("Sleep Timeout (AC)"),
            description=_("Minutes before sleep on AC power"),
            uid="sleep_timeout_ac",
            **options
        )
        
        self.set_title(_("Sleep Timeout (AC)"))
        self.set_subtitle(_("Minutes before sleep"))
        
        self._settings = GSettingsSetting("org.gnome.settings-daemon.plugins.power")
        self._updating = False
        
        ac_adjustment = Gtk.Adjustment(
            value=60,
            lower=1,
            upper=240,
            step_increment=1,
            page_increment=10
        )
        ac_spin = Gtk.SpinButton(adjustment=ac_adjustment)
        ac_spin.set_numeric(True)
        
        current_ac_timeout = self._settings.get_int("sleep-inactive-ac-timeout")
        ac_spin.set_value(current_ac_timeout / 60)
        ac_spin.connect("value-changed", self._on_timeout_changed)
        self._spin = ac_spin
        
        self.add_suffix(ac_spin)

    def _on_timeout_changed(self, spin_button):
        """Handle AC sleep timeout change"""
        if self._updating:
            return
        
        self._updating = True
        try:
            minutes = int(spin_button.get_value())
            seconds = minutes * 60
            self._settings.set_int("sleep-inactive-ac-timeout", seconds)
            LOG.debug(f"AC sleep timeout set to {minutes} minutes")
        except Exception as e:
            LOG.error(f"Failed to set AC sleep timeout: {e}")
        finally:
            self._updating = False


class SleepActionBatteryTweak(Adw.ComboRow, Tweak):
    """Control for setting battery sleep action"""
    
    def __init__(self, **options):
        Adw.ComboRow.__init__(self)
        Tweak.__init__(
            self,
            title=_("Sleep Action (Battery)"),
            description=_("What to do when timeout is reached"),
            uid="sleep_action_battery",
            **options
        )
        
        self.set_title(_("Sleep Action (Battery)"))
        self.set_subtitle(_("What to do when timeout is reached"))
        
        self._settings = GSettingsSetting("org.gnome.settings-daemon.plugins.power")
        
        action_model = Gtk.StringList()
        self._sleep_actions = [
            ('blank', _("Blank Screen")),
            ('suspend', _("Suspend")),
            ('hibernate', _("Hibernate")),
            ('shutdown', _("Shutdown")),
            ('nothing', _("Do Nothing")),
        ]
        
        for action_value, action_label in self._sleep_actions:
            action_model.append(action_label)
        
        self.set_model(action_model)
        
        current_action = self._settings.get_string("sleep-inactive-battery-type")
        for i, (action_value, action_label_text) in enumerate(self._sleep_actions):
            if action_value == current_action:
                self.set_selected(i)
                break
        
        self.connect("notify::selected", self._on_action_changed)

    def _on_action_changed(self, widget, pspec):
        """Handle battery sleep action change"""
        try:
            selected = self.get_selected()
            if 0 <= selected < len(self._sleep_actions):
                action = self._sleep_actions[selected][0]
                self._settings.set_string("sleep-inactive-battery-type", action)
                LOG.debug(f"Battery sleep action set to: {action}")
        except Exception as e:
            LOG.error(f"Failed to set battery sleep action: {e}")


class SleepActionACTweak(Adw.ComboRow, Tweak):
    """Control for setting AC sleep action"""
    
    def __init__(self, **options):
        Adw.ComboRow.__init__(self)
        Tweak.__init__(
            self,
            title=_("Sleep Action (AC)"),
            description=_("What to do when timeout is reached"),
            uid="sleep_action_ac",
            **options
        )
        
        self.set_title(_("Sleep Action (AC)"))
        self.set_subtitle(_("What to do when timeout is reached"))
        
        self._settings = GSettingsSetting("org.gnome.settings-daemon.plugins.power")
        
        action_model = Gtk.StringList()
        self._sleep_actions = [
            ('blank', _("Blank Screen")),
            ('suspend', _("Suspend")),
            ('hibernate', _("Hibernate")),
            ('shutdown', _("Shutdown")),
            ('nothing', _("Do Nothing")),
        ]
        
        for action_value, action_label in self._sleep_actions:
            action_model.append(action_label)
        
        self.set_model(action_model)
        
        current_action = self._settings.get_string("sleep-inactive-ac-type")
        for i, (action_value, action_label_text) in enumerate(self._sleep_actions):
            if action_value == current_action:
                self.set_selected(i)
                break
        
        self.connect("notify::selected", self._on_action_changed)

    def _on_action_changed(self, widget, pspec):
        """Handle AC sleep action change"""
        try:
            selected = self.get_selected()
            if 0 <= selected < len(self._sleep_actions):
                action = self._sleep_actions[selected][0]
                self._settings.set_string("sleep-inactive-ac-type", action)
                LOG.debug(f"AC sleep action set to: {action}")
        except Exception as e:
            LOG.error(f"Failed to set AC sleep action: {e}")


# Create power management tweak group
try:
    _power_settings_tweaks = []
    for tweak_class in [IdleDimTweak, SleepTimeoutBatteryTweak, SleepTimeoutACTweak, 
                        SleepActionBatteryTweak, SleepActionACTweak]:
        try:
            _power_settings_tweaks.append(tweak_class())
        except Exception as e:
            LOG.debug(f"Failed to instantiate {tweak_class.__name__}: {e}")
    
    TWEAK_GROUP = TweakPreferencesPage(
        "power",
        _("Power"),
        TweakPreferencesGroup(
            _("Battery"),
            "battery",
            BatteryStatusRow(),
        ),
        TweakPreferencesGroup(
            _("Power Profiles"),
            "profiles",
            PowerModeRow(),
        ),
        TweakPreferencesGroup(
            _("Power Settings"),
            "settings",
            *_power_settings_tweaks
        ),
        uid="power_group"
    )
except Exception as e:
    LOG.error(f"Failed to initialize power tweaks: {e}")
    TWEAK_GROUP = TweakPreferencesPage("power", _("Power"))
