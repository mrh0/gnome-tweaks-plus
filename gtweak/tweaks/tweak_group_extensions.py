# Copyright (c) 2011 John Stowers
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import logging
from gi.repository import Gtk, Adw, Gio, GLib, GObject
from gtweak.gshellwrapper import GnomeShellFactory
from gtweak.tweakmodel import Tweak, TweakGroup
from gtweak.widgets import TweakPreferencesPage, TweakPreferencesGroup, GSettingsTweakSwitchRow

LOG = logging.getLogger(__name__)

# Ensure translation function is available
try:
    _
except NameError:
    def _(msg):
        return msg


class ExtensionsEnabledTweak(GSettingsTweakSwitchRow):
    """Toggle to enable/disable all extensions"""
    def __init__(self, **options):
        try:
            GSettingsTweakSwitchRow.__init__(self,
                                            _("Disable All Extensions"),
                                            "org.gnome.shell",
                                            "disable-user-extensions",
                                            desc=_("Disable or enable all user GNOME Shell extensions"),
                                            **options)
        except Exception as e:
            LOG.warning(f"Failed to create extensions disabled tweak: {e}")
            self.loaded = False


class ExtensionRow(Adw.ExpanderRow, Tweak):
    """Widget representing a single GNOME extension with toggle switch"""

    def __init__(self, extension_info, shell_proxy, **options):
        Adw.ExpanderRow.__init__(self)
        self.uuid = extension_info.get('uuid', '')
        self.extension_info = extension_info

        title = extension_info.get('name', '') or self.uuid
        version = extension_info.get('version', '')
        description = extension_info.get('description', '')
        
        LOG.debug(f"Extension: {title}, Description: {description}")
        
        Tweak.__init__(
            self,
            title=title,
            description=description,
            uid=f"extension_{self.uuid}",
            **options
        )

        self._shell_proxy = shell_proxy
        self._updating = False

        try:
            self.set_title(title)
            
            # Show version in subtitle
            subtitle = f"v{version}" if version else _("No version")
            self.set_subtitle(subtitle)

            # Create toggle switch
            self._switch = Gtk.Switch()
            self._switch.set_valign(Gtk.Align.CENTER)
            
            # Get current enabled state
            state = extension_info.get('state', 1)  # 1 = ENABLED, 2 = DISABLED, etc.
            is_enabled = state == 1
            self._switch.set_active(is_enabled)
            self._switch.connect("notify::active", self._on_switch_toggled)

            self.add_suffix(self._switch)

            # Add description as expandable row
            if description:
                LOG.debug(f"Adding description for {title}: {description}")
                desc_row = Adw.ActionRow()
                desc_row.set_title(_("Description"))
                
                # Create a wrapped label for the description
                desc_label = Gtk.Label(label=description)
                desc_label.set_wrap(True)
                desc_label.set_halign(Gtk.Align.START)
                desc_label.set_hexpand(True)
                desc_label.set_margin_top(6)
                desc_label.set_margin_bottom(6)
                desc_label.set_margin_start(6)
                desc_label.set_margin_end(6)
                
                desc_row.set_child(desc_label)
                self.add_row(desc_row)
            else:
                LOG.debug(f"No description for {title}")
                # Add a placeholder if no description
                placeholder_row = Adw.ActionRow()
                placeholder_row.set_title(_("Description"))
                placeholder_label = Gtk.Label(label=_("No description available"))
                placeholder_label.add_css_class("dim-label")
                placeholder_row.set_child(placeholder_label)
                self.add_row(placeholder_row)

            self.widget_for_size_group = None
        except Exception as e:
            LOG.warning(f"Failed to create extension row for {self.uuid}: {e}")

    def _on_switch_toggled(self, switch, pspec):
        """Handle extension toggle"""
        if self._updating or not self._shell_proxy:
            return

        self._updating = True
        is_active = switch.get_active()

        try:
            if is_active:
                # Enable extension
                self._shell_proxy.proxy_extensions.EnableExtension('(s)', self.uuid)
            else:
                # Disable extension
                self._shell_proxy.proxy_extensions.DisableExtension('(s)', self.uuid)
            LOG.debug(f"Extension {self.uuid} toggled to {is_active}")
        except Exception as e:
            LOG.error(f"Failed to toggle extension {self.uuid}: {e}")
            # Revert switch on error
            self._updating = True
            switch.set_active(not is_active)
            self._updating = False
        finally:
            self._updating = False

    def update_state(self, new_state):
        """Update the extension state from external changes"""
        if self._updating:
            return
        
        self._updating = True
        is_enabled = new_state == 1
        self._switch.set_active(is_enabled)
        self._updating = False


def _load_extensions():
    """Load list of installed extensions from GNOME Shell"""
    shell = GnomeShellFactory().get_shell()
    
    if not shell:
        LOG.warning("GNOME Shell not available")
        return None, None

    try:
        extensions_dict = shell.list_extensions()
        
        if not extensions_dict:
            LOG.debug("No extensions found")
            return [], shell._proxy
        
        # Convert extensions dict to list of tuples
        extensions_list = []
        for uuid, info in extensions_dict.items():
            LOG.debug(f"Extension info for {uuid}: {info}")
            # Use uuid as fallback if name is missing or empty
            ext_name = info.get('name', '') or uuid
            ext_info = {
                'uuid': uuid,
                'name': ext_name,
                'description': info.get('description', ''),
                'version': info.get('version', ''),
                'state': info.get('state', 2),  # 1=ENABLED, 2=DISABLED, etc.
                'path': info.get('path', ''),
                'creator': info.get('creator', ''),
            }
            extensions_list.append(ext_info)
        
        # Sort by name (which now has uuid as fallback)
        extensions_list.sort(key=lambda x: x['name'].lower())
        
        return extensions_list, shell._proxy
    except Exception as e:
        LOG.error(f"Failed to load extensions: {e}")
        return None, None


# Load extensions and build the group
_extensions_list, _shell_proxy = _load_extensions()

# Create the toggle to enable/disable all extensions
try:
    extensions_enabled_tweak = ExtensionsEnabledTweak()
except Exception as e:
    LOG.warning(f"Failed to create extensions enabled tweak: {e}")
    extensions_enabled_tweak = None

if _extensions_list is not None and len(_extensions_list) > 0:
    # Create extension rows
    extension_rows = []
    for ext_info in _extensions_list:
        try:
            row = ExtensionRow(ext_info, _shell_proxy)
            extension_rows.append(row)
        except Exception as e:
            LOG.warning(f"Failed to create row for extension {ext_info.get('uuid')}: {e}")

    # Create a preferences group with all extensions
    if extension_rows:
        extensions_group = TweakPreferencesGroup(
            _("Installed Extensions"),
            "extensions",
            *extension_rows
        )
        
        # Build the page with extensions enabled toggle and extensions group
        page_tweaks = []
        if extensions_enabled_tweak and extensions_enabled_tweak.loaded:
            page_tweaks.append(extensions_enabled_tweak)
        page_tweaks.append(extensions_group)
        
        TWEAK_GROUP = TweakPreferencesPage(
            "extensions",
            _("Extensions"),
            *page_tweaks,
            uid="extensions_group"
        )
    else:
        # Fallback if no rows were created
        page_tweaks = []
        if extensions_enabled_tweak and extensions_enabled_tweak.loaded:
            page_tweaks.append(extensions_enabled_tweak)
        
        TWEAK_GROUP = TweakPreferencesPage(
            "extensions",
            _("Extensions"),
            *page_tweaks,
            uid="extensions_group"
        )
else:
    # Create group with just the toggle if extensions can't be loaded
    page_tweaks = []
    if extensions_enabled_tweak and extensions_enabled_tweak.loaded:
        page_tweaks.append(extensions_enabled_tweak)
    
    TWEAK_GROUP = TweakPreferencesPage(
        "extensions",
        _("Extensions"),
        *page_tweaks,
        uid="extensions_group"
    )


# Make extensions group conditional - only loaded if GNOME Shell is available
if not GnomeShellFactory().get_shell():
    TWEAK_GROUP.loaded = False
