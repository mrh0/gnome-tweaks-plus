# Copyright (c) 2011 John Stowers
# Copyright (c) 2026 MRH0
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import logging
import builtins
from gi.repository import Gtk, Adw, Gio, GLib

from gtweak.widgets import TweakPreferencesPage, GSettingsTweakSwitchRow, TweakPreferencesGroup, Tweak
from gtweak.gsettings import GSettingsSetting

LOG = logging.getLogger(__name__)

# Ensure translation function is available globally
if not hasattr(builtins, '_'):
    builtins._ = lambda msg: msg

_ = builtins._


class BlankScreenDelaySelector(Adw.ComboRow, Tweak):
    """Widget for selecting blank screen delay (idle timeout)"""
    def __init__(self, **options):
        Adw.ComboRow.__init__(self)
        Tweak.__init__(self, 
            title=_("Blank Screen Delay"),
            description=_("Period of inactivity until screen blanks"),
            **options
        )
        
        self.set_title(_("Blank Screen Delay"))
        self.set_subtitle(_("Period of inactivity until screen blanks"))
        
        self._settings = GSettingsSetting("org.gnome.desktop.session")
        self._updating = False
        
        # Create the combo model with common idle delay options
        # Times are in seconds
        model = Gtk.StringList()
        self._delay_values = [
            (60, _("1 minute")),
            (120, _("2 minutes")),
            (180, _("3 minutes")),
            (300, _("5 minutes")),
            (600, _("10 minutes")),
            (900, _("15 minutes")),
            (1800, _("30 minutes")),
            (3600, _("1 hour")),
            (0, _("Never")),
        ]
        
        for delay_secs, label in self._delay_values:
            model.append(label)
        
        self.set_model(model)
        
        # Set current value
        current_delay = self._settings.get_uint("idle-delay")
        for i, (delay_secs, label) in enumerate(self._delay_values):
            if delay_secs == current_delay:
                self.set_selected(i)
                break
        
        self.connect("notify::selected", self._on_delay_changed)

    def _on_delay_changed(self, widget, pspec):
        """Handle blank screen delay change"""
        if self._updating:
            return
        
        self._updating = True
        try:
            selected = self.get_selected()
            if 0 <= selected < len(self._delay_values):
                delay_secs = self._delay_values[selected][0]
                self._settings.set_uint("idle-delay", delay_secs)
                LOG.debug(f"Blank screen delay set to {delay_secs} seconds")
        except Exception as e:
            LOG.error(f"Failed to set blank screen delay: {e}")
        finally:
            self._updating = False


class LockScreenDelaySelector(Adw.ComboRow, Tweak):
    """Widget for selecting automatic screen lock delay"""
    def __init__(self, **options):
        Adw.ComboRow.__init__(self)
        Tweak.__init__(self,
            title=_("Automatic Screen Lock Delay"),
            description=_("Time from screen blank to screen lock"),
            **options
        )
        
        self.set_title(_("Automatic Screen Lock Delay"))
        self.set_subtitle(_("Time from screen blank to screen lock"))
        
        self._settings = GSettingsSetting("org.gnome.desktop.screensaver")
        self._updating = False
        
        # Create the combo model with lock delay options
        # Times are in seconds
        model = Gtk.StringList()
        self._delay_values = [
            (0, _("Immediately")),
            (30, _("30 seconds")),
            (60, _("1 minute")),
            (120, _("2 minutes")),
            (180, _("3 minutes")),
            (300, _("5 minutes")),
            (600, _("10 minutes")),
            (900, _("15 minutes")),
            (4294967295, _("Screen Turns Off")),
        ]
        
        for delay_secs, label in self._delay_values:
            model.append(label)
        
        self.set_model(model)
        
        # Set current value
        current_delay = self._settings.get_uint("lock-delay")
        for i, (delay_secs, label) in enumerate(self._delay_values):
            if delay_secs == current_delay:
                self.set_selected(i)
                break
        
        self.connect("notify::selected", self._on_delay_changed)

    def _on_delay_changed(self, widget, pspec):
        """Handle lock screen delay change"""
        if self._updating:
            return
        
        self._updating = True
        try:
            selected = self.get_selected()
            if 0 <= selected < len(self._delay_values):
                delay_secs = self._delay_values[selected][0]
                self._settings.set_uint("lock-delay", delay_secs)
                LOG.debug(f"Lock screen delay set to {delay_secs} seconds")
        except Exception as e:
            LOG.error(f"Failed to set lock screen delay: {e}")
        finally:
            self._updating = False


_tweaks = [
  TweakPreferencesGroup(_("General"), "general",
    BlankScreenDelaySelector(),
    GSettingsTweakSwitchRow(_("Automatic Screen Lock"),
                         schema_name="org.gnome.desktop.screensaver",
                         key_name="lock-enabled",
                         subtitle=_("Locks the screen after it blanks")),
    LockScreenDelaySelector(),
    GSettingsTweakSwitchRow(_("Lock Screen Notifications"),
                         schema_name="org.gnome.desktop.notifications",
                         key_name="show-banners",
                         subtitle=_("Show notifications on the lock screen")),
    GSettingsTweakSwitchRow(_("Lock Screen on Suspend"),
                         schema_name="org.gnome.desktop.lockdown",
                         key_name="disable-lock-screen",
                         invert_value=True,
                         subtitle=_("Require password when waking from suspend")),
  ),
]

TWEAK_GROUP = TweakPreferencesPage("screen_lock", _("Screen Lock"), *_tweaks)
