# Copyright (c) 2011 John Stowers
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import logging
from gi.repository import Gtk, Gio
from gtweak.widgets import (GSettingsTweakSwitchRow, TweakPreferencesPage, 
                            TweakPreferencesGroup, GSettingsTweakComboRow, GSettingsTweakSpinRow)
from gtweak.tweakmodel import Tweak


def _schema_exists(schema_name):
    """Check if a GSettings schema is available"""
    try:
        schemas = Gio.Settings.list_schemas()
        return schema_name in schemas
    except Exception:
        return False

# Set up translation function - gets injected by framework
try:
    _
except NameError:
    def _(msg):
        return msg


class HotCornersTweak(GSettingsTweakSwitchRow):
    """Enable hot corners"""
    def __init__(self, **options):
        GSettingsTweakSwitchRow.__init__(self,
                                        _("Hot Corner"),
                                        "org.gnome.desktop.interface",
                                        "enable-hot-corners",
                                        desc=_("Touch the top-left corner to open the Activities Overview"),
                                        **options)


class WindowTilingTweak(GSettingsTweakSwitchRow):
    """Enable window edge tiling/snapping"""
    def __init__(self, **options):
        GSettingsTweakSwitchRow.__init__(self,
                                        _("Window Snapping"),
                                        "org.gnome.mutter",
                                        "edge-tiling",
                                        desc=_("Enable window tiling when dragged to screen edges"),
                                        **options)


class DynamicWorkspacesTweak(GSettingsTweakSwitchRow):
    """Toggle between dynamic and fixed workspaces"""
    def __init__(self, **options):
        GSettingsTweakSwitchRow.__init__(self,
                                        _("Dynamic Workspaces"),
                                        "org.gnome.mutter",
                                        "dynamic-workspaces",
                                        desc=_("Automatically create and remove workspaces as needed"),
                                        **options)


class WorkspacesOnPrimaryTweak(Gtk.Box, Tweak):
    """Choose workspace display mode (primary monitor only or all displays)"""
    
    def __init__(self, **options):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=12)
        Tweak.__init__(self, _("Workspaces Display"), _("Choose where workspaces are displayed"), **options)
        
        if not _schema_exists("org.gnome.mutter"):
            raise Exception("org.gnome.mutter schema not available")
        
        self.settings = Gio.Settings.new("org.gnome.mutter")
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        
        self._primary_radio = Gtk.CheckButton.new_with_label(_("Show Workspaces Only on Primary Monitor"))
        self._span_radio = Gtk.CheckButton.new_with_label(_("Span Workspaces Across All Displays"))
        self._span_radio.set_group(self._primary_radio)
        
        # Get initial value
        primary_only = self.settings.get_boolean("workspaces-only-on-primary")
        self._primary_radio.set_active(primary_only)
        self._span_radio.set_active(not primary_only)
        
        # Connect signals
        self._primary_radio.connect('toggled', self._on_primary_toggled)
        self._span_radio.connect('toggled', self._on_span_toggled)
        
        self.settings.connect("changed::workspaces-only-on-primary", self._on_settings_changed)
        
        box.append(self._primary_radio)
        box.append(self._span_radio)
        
        self.append(box)
        self.widget_for_size_group = None
    
    def _on_primary_toggled(self, widget):
        if widget.get_active():
            self.settings.set_boolean("workspaces-only-on-primary", True)
    
    def _on_span_toggled(self, widget):
        if widget.get_active():
            self.settings.set_boolean("workspaces-only-on-primary", False)
    
    def _on_settings_changed(self, settings, key):
        primary_only = self.settings.get_boolean("workspaces-only-on-primary")
        self._primary_radio.set_active(primary_only)
        self._span_radio.set_active(not primary_only)


class NumberOfWorkspacesTweak(GSettingsTweakSpinRow):
    """Set the number of workspaces (only enabled when workspaces are fixed)"""
    def __init__(self, **options):
        GSettingsTweakSpinRow.__init__(self,
                                       _("Number of Workspaces"),
                                       "org.gnome.desktop.wm.preferences",
                                       "num-workspaces",
                                       **options)
        
        # Only enable when workspaces are fixed (not dynamic)
        if _schema_exists("org.gnome.mutter"):
            try:
                self._mutter_settings = Gio.Settings.new("org.gnome.mutter")
                # Set initial sensitivity
                self._update_sensitivity()
                # Listen for changes to dynamic-workspaces
                self._mutter_settings.connect("changed::dynamic-workspaces", self._on_dynamic_changed)
            except Exception as e:
                logging.debug(f"Could not connect to mutter settings: {e}")
                self._mutter_settings = None
        else:
            self._mutter_settings = None
    
    def _update_sensitivity(self):
        if self._mutter_settings:
            try:
                dynamic = self._mutter_settings.get_boolean("dynamic-workspaces")
                self.set_sensitive(not dynamic)
            except Exception as e:
                logging.debug(f"Error updating sensitivity: {e}")
    
    def _on_dynamic_changed(self, settings, key):
        self._update_sensitivity()


class AppSwitcherCurrentWorkspaceTweak(Gtk.Box, Tweak):
    """Choose app switcher workspace scope"""
    
    def __init__(self, **options):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=12)
        Tweak.__init__(self, _("Application Switcher"), _("Choose which windows appear in the app switcher"), **options)
        
        if not _schema_exists("org.gnome.shell.app-switcher"):
            raise Exception("org.gnome.shell.app-switcher schema not available")
        
        self.settings = Gio.Settings.new("org.gnome.shell.app-switcher")
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        
        self._current_radio = Gtk.CheckButton.new_with_label(_("Current Workspace Only"))
        self._all_radio = Gtk.CheckButton.new_with_label(_("All Workspaces"))
        self._all_radio.set_group(self._current_radio)
        
        # Get initial value
        current_only = self.settings.get_boolean("current-workspace-only")
        self._current_radio.set_active(current_only)
        self._all_radio.set_active(not current_only)
        
        # Connect signals
        self._current_radio.connect('toggled', self._on_current_toggled)
        self._all_radio.connect('toggled', self._on_all_toggled)
        
        self.settings.connect("changed::current-workspace-only", self._on_settings_changed)
        
        box.append(self._current_radio)
        box.append(self._all_radio)
        
        self.append(box)
        self.widget_for_size_group = None
    
    def _on_current_toggled(self, widget):
        if widget.get_active():
            self.settings.set_boolean("current-workspace-only", True)
    
    def _on_all_toggled(self, widget):
        if widget.get_active():
            self.settings.set_boolean("current-workspace-only", False)
    
    def _on_settings_changed(self, settings, key):
        current_only = self.settings.get_boolean("current-workspace-only")
        self._current_radio.set_active(current_only)
        self._all_radio.set_active(not current_only)


# Build groups with only successfully instantiated tweaks
try:
    _general_tweaks = []
    for tweak_class in [HotCornersTweak, WindowTilingTweak]:
        try:
            _general_tweaks.append(tweak_class())
        except Exception as e:
            logging.debug(f"Failed to instantiate {tweak_class.__name__}: {e}")

    _workspace_tweaks = []
    for tweak_class in [WorkspacesOnPrimaryTweak, DynamicWorkspacesTweak, NumberOfWorkspacesTweak]:
        try:
            _workspace_tweaks.append(tweak_class())
        except Exception as e:
            logging.debug(f"Failed to instantiate {tweak_class.__name__}: {e}")

    _app_switcher_tweaks = []
    for tweak_class in [AppSwitcherCurrentWorkspaceTweak]:
        try:
            _app_switcher_tweaks.append(tweak_class())
        except Exception as e:
            logging.debug(f"Failed to instantiate {tweak_class.__name__}: {e}")

    # Build the group with only non-empty sections
    _groups = []
    if _general_tweaks:
        _groups.append(TweakPreferencesGroup(_("General"), "general", *_general_tweaks))
    if _workspace_tweaks:
        _groups.append(TweakPreferencesGroup(_("Workspaces"), "workspaces", *_workspace_tweaks))
    if _app_switcher_tweaks:
        _groups.append(TweakPreferencesGroup(_("Application Switcher"), "app-switcher", *_app_switcher_tweaks))

    TWEAK_GROUP = TweakPreferencesPage("multitasking", _("Multitasking"), *_groups)

except Exception as e:
    logging.error(f"Failed to initialize multitasking tweaks: {e}")
    # Create empty group as fallback
    TWEAK_GROUP = TweakPreferencesPage("multitasking", _("Multitasking"))
