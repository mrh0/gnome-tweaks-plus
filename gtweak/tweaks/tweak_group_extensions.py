# Copyright (c) 2026 MRH0
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import logging
from gi.repository import Gtk, Adw, Gio, GLib, GObject
from gtweak.gshellwrapper import GnomeShellFactory
from gtweak.tweakmodel import Tweak, TweakGroup
from gtweak.widgets import TweakPreferencesPage, TweakPreferencesGroup, GSettingsTweakSwitchRow
from gtweak.gsettings import GSettingsSetting

LOG = logging.getLogger(__name__)

# Ensure translation function is available
try:
    _
except NameError:
    def _(msg):
        return msg


def _escape_markup(text):
    """Escape special characters for use in GTK markup"""
    if not text:
        return text
    text = str(text)  # Convert to string in case it's a number
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


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
        
        # Mark system extensions with an asterisk
        is_system = extension_info.get('isSystem', False)
        if is_system:
            title = f"{title} *"
        
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
            self.set_title(_escape_markup(title))
            
            # Show version in subtitle
            self.set_subtitle(self.uuid)

            # Create toggle switch
            self._switch = Gtk.Switch()
            self._switch.set_valign(Gtk.Align.CENTER)
            
            # Get current enabled state
            state = extension_info.get('state', 1)  # 1 = ENABLED, 2 = DISABLED, etc.
            is_enabled = state == 1
            self._switch.set_active(is_enabled)
            self._switch.connect("notify::active", self._on_switch_toggled)

            # Create settings button with gear icon
            settings_button = Gtk.Button()
            settings_button.set_icon_name("emblem-system-symbolic")
            settings_button.set_valign(Gtk.Align.CENTER)
            settings_button.set_tooltip_text(_("Extension Settings"))
            settings_button.connect("clicked", self._on_settings_clicked)
            
            # Disable button if extension doesn't have preferences
            has_prefs = extension_info.get('hasPrefs', False)
            settings_button.set_sensitive(has_prefs)
            if not has_prefs:
                settings_button.set_tooltip_text(_("This extension does not have settings"))
            
            self.add_prefix(settings_button)

            self.add_suffix(self._switch)

            # Add description as expandable row
            if description:
                LOG.debug(f"Adding description for {title}: {description}")
                desc_row = Adw.ActionRow()
                desc_row.set_title(_("Description"))
                desc_row.set_subtitle(_escape_markup(description))

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

            # Add version
            version_row = Adw.ActionRow()
            version_row.set_title(_("Version"))
            subtitleVersion = f"v{_escape_markup(version)}" if version else _("No version")
            version_row.set_subtitle(subtitleVersion)
            LOG.debug(f"Adding version row for {title}: {subtitleVersion}")
            self.add_row(version_row)
            LOG.debug(f"Version row added successfully")

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

    def _on_settings_clicked(self, button):
        """Open extension settings dialog"""
        try:
            if self._shell_proxy:
                # Try LaunchExtensionPrefs method
                self._shell_proxy.proxy_extensions.LaunchExtensionPrefs('(s)', self.uuid)
                LOG.debug(f"Opened preferences for extension {self.uuid}")
            else:
                LOG.warning(f"Shell proxy not available to open settings for {self.uuid}")
        except Exception as e:
            LOG.error(f"Failed to open extension settings for {self.uuid}: {e}")


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
            
            # Determine if this is a system extension (installed in system directories)
            path = info.get('path', '')
            is_system = path.startswith('/usr') or path.startswith('/app') or 'system' in path.lower()
            
            ext_info = {
                'uuid': uuid,
                'name': ext_name,
                'description': info.get('description', ''),
                'version': info.get('version', ''),
                'state': info.get('state', 2),  # 1=ENABLED, 2=DISABLED, etc.
                'path': path,
                'creator': info.get('creator', ''),
                'hasPrefs': info.get('hasPrefs', False),
                'isSystem': is_system,
            }
            extensions_list.append(ext_info)
        
        # Sort by name (which now has uuid as fallback)
        extensions_list.sort(key=lambda x: x['name'].lower())
        
        return extensions_list, shell._proxy
    except Exception as e:
        LOG.error(f"Failed to load extensions: {e}")
        return None, None


def _on_disable_all_extensions_changed(settings, key, extension_rows):
    """Handle changes to disable-user-extensions setting"""
    disable_all = settings.get_boolean(key)
    
    # Disable individual extension switches if all extensions are disabled
    for row in extension_rows:
        if hasattr(row, '_switch'):
            row._switch.set_sensitive(not disable_all)


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
        
        # Setup listener for disable-all-extensions setting
        try:
            shell_settings = GSettingsSetting("org.gnome.shell")
            
            # Set initial sensitivity based on current setting
            disable_all = shell_settings.get_boolean("disable-user-extensions")
            for row in extension_rows:
                if hasattr(row, '_switch'):
                    row._switch.set_sensitive(not disable_all)
            
            # Connect to setting changes
            shell_settings.connect("changed::disable-user-extensions", 
                                   _on_disable_all_extensions_changed, 
                                   extension_rows)
        except Exception as e:
            LOG.warning(f"Failed to setup disable-all-extensions listener: {e}")
        
        # Build the page with extensions enabled toggle and extensions group
        page_tweaks = []
        if extensions_enabled_tweak and extensions_enabled_tweak.loaded:
            general_group = TweakPreferencesGroup(
                _("General"),
                "general",
                extensions_enabled_tweak
            )
            page_tweaks.append(general_group)
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
            general_group = TweakPreferencesGroup(
                _("General"),
                "general",
                extensions_enabled_tweak
            )
            page_tweaks.append(general_group)
        
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
        general_group = TweakPreferencesGroup(
            _("General"),
            "general",
            extensions_enabled_tweak
        )
        page_tweaks.append(general_group)
    
    TWEAK_GROUP = TweakPreferencesPage(
        "extensions",
        _("Extensions"),
        *page_tweaks,
        uid="extensions_group"
    )


# Make extensions group conditional - only loaded if GNOME Shell is available
if not GnomeShellFactory().get_shell():
    TWEAK_GROUP.loaded = False
