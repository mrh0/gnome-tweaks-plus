# Copyright (c) 2011 John Stowers
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import gi
import logging
gi.require_version("GnomeDesktop", "4.0")
from gi.repository import Gtk, GnomeDesktop, Gtk, Adw, Gio, Pango

from gtweak.gshellwrapper import GnomeShellFactory
from gtweak.widgets import TweakPreferencesPage, GSettingsTweakSwitchRow, GSettingsSwitchTweakValue, _GSettingsTweak, TweakPreferencesGroup, build_label_beside_widget, Tweak, GSettingsTweakComboRow, TweakListStoreItem
from gtweak.tweakmodel import Tweak, TweakGroup
from gtweak.gsettings import GSettingsSetting, GSettingsMissingError



_shell = GnomeShellFactory().get_shell()
_shell_loaded = _shell is not None


class _XkbOption(Gtk.Expander, Tweak):
    def __init__(self, group_id, parent_settings, xkb_info, **options):
        try:
            desc = xkb_info.description_for_group(group_id)
        except AttributeError:
            desc = group_id
        Gtk.Expander.__init__(self)
        Tweak.__init__(self, desc, desc, **options)

        self.set_label(self.title)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.set_margin_start(15)
        self.set_child(vbox)

        self._multiple_selection = group_id not in { 'keypad', 'kpdl', 'caps', 'altwin', 'nbsp', 'esperanto' }
        self._group_id = group_id
        self._parent_settings = parent_settings
        self._xkb_info = xkb_info
        self._possible_values = []

        model_values = []
        if not self._multiple_selection:
            model_values.append((None, _("Default")))

        for option_id in self._xkb_info.get_options_for_group(group_id):
            desc = self._xkb_info.description_for_option(group_id, option_id)
            model_values.append((option_id, desc))
            self._possible_values.append(option_id)

        def values_cmp_py3_wrap(f):
            ''' https://docs.python.org/3/howto/sorting.html#the-old-way-using-the-cmp-parameter '''
            class C:
                def __init__(self, obj, *args):
                    self.obj = obj
                def __lt__(self, other):
                    return f(self.obj, other.obj) < 0
                def __gt__(self, other):
                    return f(self.obj, other.obj) > 0
                def __eq__(self, other):
                    return f(self.obj, other.obj) == 0
                def __le__(self, other):
                    return f(self.obj, other.obj) <= 0
                def __ge__(self, other):
                    return f(self.obj, other.obj) >= 0
                def __ne__(self, other):
                    return f(self.obj, other.obj) != 0
            return C

        def values_cmp(xxx_todo_changeme, xxx_todo_changeme1):
            (av, ad) = xxx_todo_changeme
            (bv, bd) = xxx_todo_changeme1
            if not av:
                return -1
            elif not bv:
                return 1
            else:
                return (ad > bd) - (ad < bd)
        model_values.sort(key=values_cmp_py3_wrap(values_cmp))

        self._widgets = dict()
        for (val, name) in model_values:
            w = Gtk.CheckButton.new_with_label(name)
            if not self._multiple_selection:
                w.set_group(self._widgets.get(None))

            self._widgets[val] = w
            vbox.append(w)
            w._changed_id = w.connect('toggled', self._on_toggled)
            w._val = val

        self.widget_for_size_group = None
        self.reload()

    def reload(self):
        self._values = []
        for v in self._parent_settings.get_strv(TypingTweakGroup.XKB_GSETTINGS_NAME):
            if (v in self._possible_values):
                self._values.append(v)

        self._update_checks()

    def _update_checks(self):
        if len(self._values) > 0:
            self.set_label('<b>'+self.title+'</b>')
            self.set_use_markup(True)
        else:
            self.set_label(self.title)

        def _set_active(w, active):
            w.disconnect(w._changed_id)
            w.set_active(active)
            w._changed_id = w.connect('toggled', self._on_toggled)

        if not self._multiple_selection:
            if len(self._values) > 0:
                w = self._widgets.get(self._values[0])
                if w:
                    _set_active(w, True)
        else:
            for w in list(self._widgets.values()):
                if w._val in self._values:
                    _set_active(w, True)
                else:
                    _set_active(w, False)

    def _on_toggled(self, w):
        active = w.get_active()
        if not self._multiple_selection and active:
            for v in self._values:
                self._parent_settings.setting_remove_from_list(TypingTweakGroup.XKB_GSETTINGS_NAME, v)

        if w._val in self._values and not active:
            self._parent_settings.setting_remove_from_list(TypingTweakGroup.XKB_GSETTINGS_NAME, w._val)
        elif active and not w._val in self._values and w._val:
            self._parent_settings.setting_add_to_list(TypingTweakGroup.XKB_GSETTINGS_NAME, w._val)

class InputSourceSwitchingTweak(Gtk.Box, _GSettingsTweak):
    """Toggle for per-window input source switching"""
    
    def __init__(self, **options):
        name = _("Input Source Switching")
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=12)
        _GSettingsTweak.__init__(self, name, "org.gnome.desktop.input-sources", "per-window", **options)

        # Create a box for the radio actions
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        
        # Create radio actions
        self._same_source = Gtk.CheckButton.new_with_label(_("Use the same source for all windows"))
        self._per_window = Gtk.CheckButton.new_with_label(_("Switch input sources individually for each window"))
        self._per_window.set_group(self._same_source)

        # Get initial value
        per_window = self.settings.get_boolean(self.key_name)
        self._same_source.set_active(not per_window)
        self._per_window.set_active(per_window)

        # Connect signals
        self._same_source.connect('toggled', self._on_same_source_toggled)
        self._per_window.connect('toggled', self._on_per_window_toggled)

        # Connect to settings changes
        self._settings_id = self.settings.connect("changed::" + self.key_name, self._on_settings_changed)

        box.append(self._same_source)
        box.append(self._per_window)
        
        self.append(box)
        self.connect("destroy", self._on_destroy)

    def _on_same_source_toggled(self, widget):
        if widget.get_active():
            self.settings.set_boolean(self.key_name, False)

    def _on_per_window_toggled(self, widget):
        if widget.get_active():
            self.settings.set_boolean(self.key_name, True)

    def _on_settings_changed(self, settings, key):
        per_window = self.settings.get_boolean(self.key_name)
        self._same_source.set_active(not per_window)
        self._per_window.set_active(per_window)

    def _on_destroy(self, widget):
        if self._settings_id:
            self.settings.disconnect(self._settings_id)


class XkbModifierSelectorComboRow(Adw.ComboRow, _GSettingsTweak):
    """Combo row selector for XKB modifier options using the standard dropdown UI"""
    
    def __init__(self, title, option_prefix, options_list, **options):
        """
        Initialize the modifier selector
        
        Args:
            title: Display name for this tweak
            option_prefix: Prefix to look for in xkb-options (e.g., "lv3:", "compose:")
            options_list: List of (key_name, display_name) tuples
        """
        _GSettingsTweak.__init__(self, title, "org.gnome.desktop.input-sources", "xkb-options", **options)
        Adw.ComboRow.__init__(self, title=title)

        self.option_prefix = option_prefix
        self.options_list = options_list
        self.loaded = True
        self.widget_for_size_group = self
        
        # Build model with Disabled option + all options
        model_items = [TweakListStoreItem(value="", title=_("Disabled"))]
        for key, display_name in options_list:
            model_items.append(TweakListStoreItem(value=key, title=display_name))
        
        store = Gio.ListStore()
        for item in model_items:
            store.append(item)
        
        self.set_model(store)
        
        # Set up factory for rendering
        factory = Gtk.SignalListItemFactory()
        factory.connect('setup', self._factory_setup)
        factory.connect('bind', self._factory_bind)
        self.set_factory(factory)
        
        # Load current value and listen for changes
        self.settings.connect('changed::xkb-options', self._on_settings_changed)
        self._update_combo_for_setting()
        
        # Connect to combo changes
        self.connect('notify::selected-item', self._on_combo_changed)

    def _factory_setup(self, factory, item):
        label = Gtk.Label(xalign=0.0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=20, valign=Gtk.Align.CENTER)
        item.set_child(label)

    def _factory_bind(self, factory, item):
        label = item.get_child()
        if label and item.get_item():
            label.set_label(item.get_item().title)

    def _get_current_option(self):
        """Get the current option value from xkb-options array"""
        xkb_options = self.settings.get_strv("xkb-options")
        for option in xkb_options:
            if option.startswith(self.option_prefix):
                return option
        return ""

    def _update_combo_for_setting(self):
        """Update combo box to show current value"""
        current = self._get_current_option()
        model = self.get_model()
        
        for i in range(len(model)):
            if model[i].value == current:
                self.set_selected(i)
                return
        
        # If not found, select disabled (first item)
        self.set_selected(0)

    def _on_settings_changed(self, settings, key):
        """Handle external settings changes"""
        self._update_combo_for_setting()

    def _on_combo_changed(self, combo, pspec):
        """Handle combo box selection changes"""
        selected_item = self.get_selected_item()
        if selected_item is None:
            return
        
        new_value = selected_item.value
        xkb_options = list(self.settings.get_strv("xkb-options"))
        
        # Remove any existing option with this prefix
        xkb_options = [opt for opt in xkb_options if not opt.startswith(self.option_prefix)]
        
        # Add new value if not disabled
        if new_value:
            xkb_options.append(new_value)
        
        self.settings.set_strv("xkb-options", xkb_options)



class KeyboardShortcutsTweak(Adw.ActionRow, Tweak):
    """Navigation row to open keyboard shortcuts dialog"""
    
    def __init__(self, **options):
        Adw.ActionRow.__init__(self)
        Tweak.__init__(self, "keyboard-shortcuts", "", **options)
        
        self.set_title(_("View and Customize Shortcuts"))
        self.set_activatable(True)
        
        # Required by tweaks framework
        self.loaded = True
        self.widget_for_size_group = None
        
        # Add arrow suffix
        arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
        self.add_suffix(arrow)
        
        # Connect to activated signal
        self.connect("activated", self._on_activated)
    
    def _on_activated(self, row):
        """Open keyboard shortcuts settings"""
        import subprocess
        try:
            subprocess.Popen(["gnome-control-center", "keyboard", "shortcuts"])
        except Exception as e:
            logging.warning("Failed to open keyboard shortcuts: %s" % e)


class TypingTweakGroup(Gtk.Box):

    XKB_GSETTINGS_SCHEMA = "org.gnome.desktop.input-sources"
    XKB_GSETTINGS_NAME = "xkb-options"
    # grp_led is unsupported
    XKB_OPTIONS_BLACKLIST = {"grp_led", "Compose key"}

    def __init__(self):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self._option_objects = []
        ok = False
        try:
            self._kbdsettings = GSettingsSetting(self.XKB_GSETTINGS_SCHEMA)
            self._kdb_settings_id = self._kbdsettings.connect("changed::"+self.XKB_GSETTINGS_NAME, self._on_changed)
            self._xkb_info = GnomeDesktop.XkbInfo()
            ok = True
            self.loaded = True
        except GSettingsMissingError:
            logging.info("Typing missing schema %s" % self.XKB_GSETTINGS_SCHEMA)
            self.loaded = False
        except AttributeError:
            logging.warning("Typing missing GnomeDesktop.gir with Xkb support")
            self.loaded = False
        finally:
            if ok:
                for opt in set(self._xkb_info.get_all_option_groups()) - self.XKB_OPTIONS_BLACKLIST:
                    obj = _XkbOption(opt, self._kbdsettings, self._xkb_info)
                    self._option_objects.append(obj)
                self._option_objects.sort(key=lambda item_desc: item_desc.title)
                for item in self._option_objects:
                    self.append(item)
        TweakGroup.__init__(self, _("Typing"), *self._option_objects)

        self.connect("destroy", self._on_destroy)

    def _on_changed(self, *args):
        for obj in self._option_objects:
            obj.reload()

    def _on_destroy(self, event):
        if (self._kdb_settings_id):
            self._kbdsettings.disconnect(self._kdb_settings_id)



class KeyThemeSwitcher(GSettingsSwitchTweakValue):
    def __init__(self, **options):
        GSettingsSwitchTweakValue.__init__(self,
                                           _("Emacs Input"),
                                           "org.gnome.desktop.interface",
                                           "gtk-key-theme",
                                           desc=_("Overrides shortcuts to use keybindings from the Emacs editor."),
                                           **options)

    def get_active(self):
        return "Emacs" in self.settings.get_string(self.key_name)

    def set_active(self, v):
        if v:
            self.settings.set_string(self.key_name, "Emacs")
        else:
            self.settings.set_string(self.key_name, "Default")


class OverviewShortcutTweak(Gtk.Box, _GSettingsTweak):

    def __init__(self, **options):
        name = _("Overview Shortcut")
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        _GSettingsTweak.__init__(self, name, "org.gnome.mutter", "overlay-key", loaded=_shell_loaded, **options)

        box_btn = Gtk.Box()
        box_btn.set_homogeneous(True)
        box_btn.add_css_class("linked")

        btn1 = Gtk.ToggleButton.new_with_label(_("Left Super"))
        btn2 = Gtk.ToggleButton.new_with_label(_("Right Super"))
        btn2.set_group(btn1)

        if self.settings.get_string(self.key_name) == "Super_R":
            btn2.set_active(True)
        elif self.settings.get_string(self.key_name) == "Super_L":
            btn1.set_active(True)

        btn1.connect("toggled", self.on_button_toggled, "Super_L")
        btn2.connect("toggled", self.on_button_toggled, "Super_R")

        box_btn.append(btn1)
        box_btn.append(btn2)
        build_label_beside_widget(name, box_btn, hbox=self)

    def on_button_toggled(self, button, key):
        self.settings[self.key_name] = key


class AdditionalLayoutButton(Adw.ActionRow, Tweak):

    def __init__(self):
        Adw.ActionRow.__init__(self)
        Tweak.__init__(self, "extensions", "")

        self.set_title(_("Additional Layout Options"))
        self.set_activatable(True)
        
        # Required by tweaks framework
        self.loaded = True
        self.widget_for_size_group = None
        
        # Add arrow suffix
        arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
        self.add_suffix(arrow)
        
        self.connect("activated", self._on_activated)

    def _on_activated(self, row):
        dialog = Gtk.Dialog()
        dialog.set_title(_("Additional Layout Options"))
        dialog.set_transient_for(self.main_window)
        dialog.set_modal(True)
        dialog.set_size_request(500, 500)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_margin_top(10)
        scrolled_window.set_margin_start(10)
        box = TypingTweakGroup()
        scrolled_window.set_child(box)

        dialog.set_child(scrolled_window)
        dialog.show()


TWEAK_GROUP = TweakPreferencesPage("keyboard", _("Keyboard"),
                                      TweakPreferencesGroup(
                                          _("Input Sources"),    "input-sources",
                                          GSettingsTweakSwitchRow(_("Show Extended Input Sources"),
                              "org.gnome.desktop.input-sources",
                              "show-all-sources",
                              desc=_("Increases the choice of input sources in the Settings application."),
                              logout_required=True,),
                                          InputSourceSwitchingTweak(),
                                      ),
                                      TweakPreferencesGroup(
                                          _("Special Character Entry"), "character-entry",
                                          XkbModifierSelectorComboRow(
                                              _("Alternate Characters Key"),
                                              "lv3:",
                                              [
                                                  ("lv3:lalt_switch", _("Left Alt")),
                                                  ("lv3:ralt_switch", _("Right Alt")),
                                                  ("lv3:lwin_switch", _("Left Super")),
                                                  ("lv3:rwin_switch", _("Right Super")),
                                                  ("lv3:menu_switch", _("Menu key")),
                                                  ("lv3:switch", _("Right Ctrl")),
                                              ]
                                          ),
                                          XkbModifierSelectorComboRow(
                                              _("Compose Key"),
                                              "compose:",
                                              [
                                                  ("compose:ralt", _("Right Alt")),
                                                  ("compose:lwin", _("Left Super")),
                                                  ("compose:rwin", _("Right Super")),
                                                  ("compose:menu", _("Menu key")),
                                                  ("compose:lctrl", _("Left Ctrl")),
                                                  ("compose:rctrl", _("Right Ctrl")),
                                                  ("compose:caps", _("Caps Lock")),
                                                  ("compose:sclk", _("Scroll Lock")),
                                                  ("compose:prsc", _("Print Screen")),
                                                  ("compose:ins", _("Insert")),
                                              ]
                                          ),
                                      ),
                                      TweakPreferencesGroup(
                                          _("Keyboard Shortcuts"), "keyboard-shortcuts",
                                          KeyboardShortcutsTweak(),
                                      ),
                                      TweakPreferencesGroup(
                                          _("Layout"), "keyboard-layout",
                                          KeyThemeSwitcher(),
                                          OverviewShortcutTweak(),
                                          AdditionalLayoutButton(),
                                      )
)
