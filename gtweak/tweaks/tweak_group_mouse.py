# Copyright (c) 2011 John Stowers
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import logging
from gi.repository import GDesktopEnums, Gtk, Adw, Gio, GLib
from gtweak.devicemanager import pointing_stick_is_present, touchpad_is_present

from gtweak.widgets import (GSettingsTweakComboRow, TweakPreferencesPage, GSettingsTweakSwitchRow, 
                            GSettingsSwitchTweakValue, TweakPreferencesGroup, Tweak)

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

class PointerAccelProfile(GSettingsSwitchTweakValue):

    def __init__(self, title, description, peripheral_type, **options):
        GSettingsSwitchTweakValue.__init__(self,
                                           title=title,
                                           schema_name="org.gnome.desktop.peripherals",
                                           schema_id=f"org.gnome.desktop.peripherals.{peripheral_type}",
                                           schema_child_name=peripheral_type,
                                           key_name="accel-profile",
                                           desc=description,
                                           **options)

    def get_active(self):
        return self.settings.get_enum(self.key_name) != GDesktopEnums.PointerAccelProfile.FLAT
    
    def set_active(self, v):
        if not v:
          self.settings.set_enum(self.key_name, GDesktopEnums.PointerAccelProfile.FLAT)
        else:
          self.settings.reset(self.key_name)


class ClickMethod(GSettingsSwitchTweakValue):

    def __init__(self, **options):
        title = _("Disable Secondary Click")
        desc = _("Disables secondary clicks on touchpads which do not have a physical secondary button")

        GSettingsSwitchTweakValue.__init__(self,
                                           title=title,
                                           schema_name="org.gnome.desktop.peripherals",
                                           schema_child_name="touchpad",
                                           schema_id="org.gnome.desktop.peripherals.touchpad",
                                           key_name="click-method",
                                           desc=desc,
                                           **options)

    def get_active(self):
        return self.settings.get_enum(self.key_name) == GDesktopEnums.TouchpadClickMethod.NONE
    
    def set_active(self, v):
        if v:
          self.settings.set_enum(self.key_name, GDesktopEnums.TouchpadClickMethod.NONE)
        else:
          self.settings.reset(self.key_name)


class PrimaryButtonSelector(Adw.ActionRow, Tweak):
    """Widget for selecting primary mouse button (Left/Right)"""
    def __init__(self, **options):
        Adw.ActionRow.__init__(self)
        Tweak.__init__(self, title=_("Primary Button"), 
                      description=_("Order of physical buttons on mice and touchpads"), 
                      **options)
        
        self.set_title(_("Primary Button"))
        self.set_subtitle(_("Order of physical buttons on mice and touchpads"))
        
        try:
            self._settings = Gio.Settings.new("org.gnome.desktop.peripherals.mouse")
        except:
            self._settings = None
            return
        
        # Create a box to hold the button boxes
        toggle_box = Gtk.Box(spacing=0)
        toggle_box.set_homogeneous(True)
        toggle_box.set_vexpand(False)
        toggle_box.set_valign(Gtk.Align.CENTER)
        toggle_box.add_css_class("linked")
        
        # Create Left button
        self._left_button = Gtk.ToggleButton.new_with_label(_("Left"))
        self._left_button.set_valign(Gtk.Align.CENTER)
        self._left_button.set_vexpand(False)
        toggle_box.append(self._left_button)
        
        # Create Right button
        self._right_button = Gtk.ToggleButton.new_with_label(_("Right"))
        self._right_button.set_valign(Gtk.Align.CENTER)
        self._right_button.set_vexpand(False)
        self._right_button.set_group(self._left_button)
        toggle_box.append(self._right_button)
        
        # Set initial state
        left_handed = self._settings.get_boolean("left-handed")
        if left_handed:
            self._left_button.set_active(True)
        else:
            self._right_button.set_active(True)
        
        # Connect signals
        self._left_button.connect("toggled", self._on_button_toggled)
        self._right_button.connect("toggled", self._on_button_toggled)
        
        # Monitor settings changes from outside
        self._settings.connect("changed::left-handed", self._on_settings_changed)
        
        # Add to row
        self.add_suffix(toggle_box)
        self.set_activatable_widget(toggle_box)
        
        self.widget_for_size_group = None
    
    def _on_button_toggled(self, button):
        """Handle button toggle"""
        if not self._settings or not button.get_active():
            return
        
        left_handed = button == self._left_button
        
        try:
            self._settings.set_boolean("left-handed", left_handed)
        except Exception as e:
            logging.warning(f"Failed to set primary button: {e}")
    
    def _on_settings_changed(self, settings, key):
        """Handle external settings changes"""
        if key == "left-handed":
            left_handed = settings.get_boolean(key)
            if left_handed:
                self._left_button.set_active(True)
            else:
                self._right_button.set_active(True)


class PointerSpeedSlider(Adw.ActionRow, Tweak):
    """Widget for controlling pointer speed"""
    def __init__(self, peripheral_type="mouse", **options):
        Adw.ActionRow.__init__(self)
        Tweak.__init__(self, title=_("Pointer Speed"), description="", **options)
        
        self._peripheral_type = peripheral_type
        self._schema_name = "org.gnome.desktop.peripherals"
        self._schema_id = f"org.gnome.desktop.peripherals.{peripheral_type}"
        self._schema_child_name = peripheral_type
        self._speed_timeout_id = None
        
        try:
            self._settings = Gio.Settings.new_with_path(
                self._schema_id,
                f"/org/gnome/desktop/peripherals/{peripheral_type}/"
            )
        except:
            self._settings = None
            return
        
        self.set_title(_("Pointer Speed"))
        self.set_activatable_widget(None)
        
        # Create scale widget
        adjustment = Gtk.Adjustment(lower=-1, upper=1, step_increment=0.1, page_increment=0.1)
        self._scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        self._scale.set_hexpand(True)
        self._scale.set_draw_value(False)
        self._scale.set_size_request(200, -1)
        
        # Add marks
        self._scale.add_mark(-1.0, Gtk.PositionType.BOTTOM, _("Slow"))
        self._scale.add_mark(0.0, Gtk.PositionType.BOTTOM, None)
        self._scale.add_mark(1.0, Gtk.PositionType.BOTTOM, _("Fast"))
        
        # Set current value
        current_speed = self._settings.get_double("speed")
        self._scale.set_value(current_speed)
        
        # Connect signals - debounce value changes
        self._scale.connect("value-changed", self._on_speed_changed)
        
        # Also monitor external changes
        self._settings.connect("changed::speed", self._on_settings_changed)
        
        # Add to row
        self.add_suffix(self._scale)
        
        self.widget_for_size_group = None
    
    def _on_speed_changed(self, scale):
        """Handle speed slider change - debounce with timeout"""
        if not self._settings:
            return
        
        # Cancel previous timeout if any
        if self._speed_timeout_id is not None:
            GLib.source_remove(self._speed_timeout_id)
        
        # Set a new timeout to apply the change after user stops dragging
        self._speed_timeout_id = GLib.timeout_add(300, self._apply_speed_setting)
        
        self.widget_for_size_group = None
    
    def _apply_speed_setting(self):
        """Apply the speed setting after debounce timeout"""
        if not self._settings:
            return False
        
        self._speed_timeout_id = None
        value = self._scale.get_value()
        try:
            self._settings.set_double("speed", value)
        except Exception as e:
            logging.warning(f"Failed to set pointer speed: {e}")
        
        return False  # Don't repeat timeout
    
    def _on_settings_changed(self, settings, key):
        """Handle external settings changes"""
        if key == "speed":
            new_value = settings.get_double(key)
            self._scale.set_value(new_value)


class ScrollDirectionSelector(GSettingsTweakComboRow):
    """Widget for selecting scroll direction (Traditional/Natural)"""
    def __init__(self, peripheral_type="mouse", **options):
        GSettingsTweakComboRow.__init__(self,
            title=_("Scroll Direction"),
            schema_name="org.gnome.desktop.peripherals",
            schema_child_name=peripheral_type,
            schema_id=f"org.gnome.desktop.peripherals.{peripheral_type}",
            key_name="natural-scroll",
            **options
        )


class MouseTestWindow(Adw.Window):
    """Window for testing mouse button clicks"""
    def __init__(self, parent=None, **options):
        Adw.Window.__init__(self)
        
        self.set_title(_("Test Mouse Buttons"))
        self.set_modal(True)
        if parent:
            self.set_transient_for(parent)
        self.set_default_size(600, 400)
        
        self._reset_timeout_id = None
        
        try:
            mouse_settings = Gio.Settings.new("org.gnome.desktop.peripherals.mouse")
            self._double_click_delay = mouse_settings.get_int("double-click")
        except:
            self._double_click_delay = 400
        
        # Create main vertical box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Add header bar for window controls
        header_bar = Adw.HeaderBar()
        main_box.append(header_bar)
        
        # Create content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content_box.set_margin_top(12)
        content_box.set_margin_bottom(12)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        content_box.set_vexpand(True)
        content_box.set_halign(Gtk.Align.CENTER)
        content_box.set_valign(Gtk.Align.CENTER)
        
        # Create test area with overlay for centered text
        test_overlay = Gtk.Overlay()
        
        self._test_button = Gtk.DrawingArea()
        self._test_button.set_size_request(200, 200)
        self._test_button.add_css_class("test-button")
        self._test_button.set_draw_func(self._draw_test_button)
        
        # Add an overlay label for click text centered on the button
        test_label = Gtk.Label(label=_("Click Here"))
        test_label.add_css_class("test-button-label")
        test_label.set_halign(Gtk.Align.CENTER)
        test_label.set_valign(Gtk.Align.CENTER)
        
        # Track click state for double-click detection
        self._last_click_button = None
        self._last_click_time = 0
        self._double_click_timeout_id = None
        
        # Add click gesture to the overlay (which covers both DrawingArea and Label)
        gesture = Gtk.GestureClick.new()
        gesture.set_button(0)  # 0 = accepts all mouse buttons
        gesture.connect("pressed", self._on_test_button_pressed)
        test_overlay.add_controller(gesture)
        
        # Set up overlay with DrawingArea as child and Label as overlay
        test_overlay.set_child(self._test_button)
        test_overlay.add_overlay(test_label)
        
        # Center the overlay in the content box
        test_overlay.set_halign(Gtk.Align.CENTER)
        test_overlay.set_valign(Gtk.Align.CENTER)
        content_box.append(test_overlay)
        
        # Create indicators box
        indicators_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        indicators_box.set_halign(Gtk.Align.CENTER)
        
        # Primary click indicator
        primary_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._primary_indicator = Gtk.DrawingArea()
        self._primary_indicator.set_size_request(40, 40)
        self._primary_indicator.set_draw_func(self._draw_indicator_circle, "primary")
        self._primary_indicator.add_css_class("indicator-circle")
        primary_label = Gtk.Label(label=_("Primary Click"))
        primary_box.append(self._primary_indicator)
        primary_box.append(primary_label)
        
        # Secondary click indicator
        secondary_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._secondary_indicator = Gtk.DrawingArea()
        self._secondary_indicator.set_size_request(40, 40)
        self._secondary_indicator.set_draw_func(self._draw_indicator_circle, "secondary")
        self._secondary_indicator.add_css_class("indicator-circle")
        secondary_label = Gtk.Label(label=_("Secondary Click"))
        secondary_box.append(self._secondary_indicator)
        secondary_box.append(secondary_label)
        
        # Double click indicator
        double_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._double_indicator = Gtk.DrawingArea()
        self._double_indicator.set_size_request(40, 40)
        self._double_indicator.set_draw_func(self._draw_indicator_circle, "double")
        self._double_indicator.add_css_class("indicator-circle")
        double_label = Gtk.Label(label=_("Double Click"))
        double_box.append(self._double_indicator)
        double_box.append(double_label)
        
        indicators_box.append(primary_box)
        indicators_box.append(secondary_box)
        indicators_box.append(double_box)
        
        content_box.append(indicators_box)
        main_box.append(content_box)
        
        self.set_content(main_box)
        
        # Store indicator states
        self._indicators = {
            "primary": False,
            "secondary": False,
            "double": False
        }
    
    def _draw_indicator_circle(self, area, ctx, width, height, user_data):
        """Draw indicator circle"""
        is_active = self._indicators.get(user_data, False)
        
        if is_active:
            # Green circle when active
            ctx.set_source_rgb(0.2, 0.8, 0.2)
        else:
            # Gray circle when inactive
            ctx.set_source_rgb(0.5, 0.5, 0.5)
        
        ctx.arc(width / 2, height / 2, min(width, height) / 2 - 2, 0, 2 * 3.14159)
        ctx.fill()
    
    def _on_test_button_pressed(self, gesture, n_press, x, y):
        """Handle test button press - just track which button"""
        import time
        
        button = gesture.get_current_button()
        current_time = time.time()
        
        # Debug output
        print(f"Click detected: button={button}, n_press={n_press}, time={current_time}, last_button={self._last_click_button}")
        
        # Check for double-click (same button within double-click delay)
        is_double_click = (
            button == self._last_click_button and
            (current_time - self._last_click_time) < (self._double_click_delay / 1000.0)
        )
        
        # Cancel any pending double-click detection
        if self._double_click_timeout_id is not None:
            GLib.source_remove(self._double_click_timeout_id)
            self._double_click_timeout_id = None
        
        # Cancel indicator reset timeout
        if self._reset_timeout_id is not None:
            GLib.source_remove(self._reset_timeout_id)
        
        # Reset all indicators
        self._indicators = {
            "primary": False,
            "secondary": False,
            "double": False
        }
        
        # Update indicators based on button type
        if button == 1:  # Primary button (left)
            if is_double_click:
                print("  -> Setting DOUBLE click")
                self._indicators["double"] = True
            else:
                print("  -> Setting PRIMARY click")
                self._indicators["primary"] = True
        elif button == 3:  # Secondary button (right)
            print("  -> Setting SECONDARY click")
            self._indicators["secondary"] = True
        else:
            print(f"  -> Unknown button: {button}")
        
        # Redraw all indicators
        self._primary_indicator.queue_draw()
        self._secondary_indicator.queue_draw()
        self._double_indicator.queue_draw()
        
        # Reset indicators after delay
        self._reset_timeout_id = GLib.timeout_add(self._double_click_delay * 2, self._reset_indicators)
        
        # Store click info for double-click detection
        self._last_click_button = button
        self._last_click_time = current_time
    
    def _on_test_button_released(self, gesture, n_press, x, y):
        """Handle button release"""
        pass  # We handle everything in pressed for now
    
    def _draw_test_button(self, area, ctx, width, height, user_data):
        """Draw the test button background"""
        # Draw gray background
        ctx.set_source_rgb(0.2, 0.2, 0.2)
        ctx.rectangle(0, 0, width, height)
        ctx.fill()
        
        # Draw border
        ctx.set_source_rgb(0.5, 0.5, 0.5)
        ctx.set_line_width(2)
        ctx.rectangle(1, 1, width - 2, height - 2)
        ctx.stroke()
    
    def _reset_indicators(self):
        """Reset all indicators"""
        self._reset_timeout_id = None
        self._indicators = {
            "primary": False,
            "secondary": False,
            "double": False
        }
        self._primary_indicator.queue_draw()
        self._secondary_indicator.queue_draw()
        self._double_indicator.queue_draw()
        return False


class TestButton(Gtk.Button, Tweak):
    """Button to open mouse test window"""
    def __init__(self, **options):
        Gtk.Button.__init__(self, label=_("Test Buttons"))
        Tweak.__init__(self, title="", description="", **options)
        
        self._test_window = None
        self.connect("clicked", self._on_clicked)
        self.widget_for_size_group = None
    
    def _on_clicked(self, button):
        """Open mouse test window"""
        if self._test_window is None or not self._test_window.get_visible():
            self._test_window = MouseTestWindow()
            self._test_window.present()
        else:
            self._test_window.close()


_tweaks = [
  TweakPreferencesGroup(_("General"), "general",
    PrimaryButtonSelector(),
  ),
  TweakPreferencesGroup(_("Mouse"), "mouse",
    PointerSpeedSlider(peripheral_type="mouse"),
    PointerAccelProfile(
        title=_("Mouse Acceleration"),
        description=_("Recommended for most users and applications"),
        peripheral_type="mouse",
    ),
    GSettingsTweakSwitchRow(_("Natural Scrolling"),
                         schema_name="org.gnome.desktop.peripherals",
                         schema_child_name="mouse",
                         schema_id="org.gnome.desktop.peripherals.mouse",
                         key_name="natural-scroll"),
    GSettingsTweakSwitchRow(_("Middle Click Paste"),
                         schema_name="org.gnome.desktop.interface",
                         key_name="gtk-enable-primary-paste"),
    TestButton(),
  ),
]

if touchpad_is_present():
  _tweaks += [
    TweakPreferencesGroup(_("Touchpad"), "touchpad",
      PointerSpeedSlider(peripheral_type="touchpad"),
      PointerAccelProfile(
        title=_("Touchpad Acceleration"),
        description=_("Turning acceleration off can allow faster and more precise movements, but can also make the touchpad more difficult to use."),
        peripheral_type="touchpad",
      ),
      ClickMethod(),
      GSettingsTweakSwitchRow(_("Natural Scrolling"),
                           schema_name="org.gnome.desktop.peripherals",
                           schema_child_name="touchpad",
                           schema_id="org.gnome.desktop.peripherals.touchpad",
                           key_name="natural-scroll"),
      GSettingsTweakSwitchRow(_("Tap to Click"),
                           schema_name="org.gnome.desktop.peripherals",
                           schema_child_name="touchpad",
                           schema_id="org.gnome.desktop.peripherals.touchpad",
                           key_name="tap-to-click"),
      GSettingsTweakSwitchRow(_("Disable While Typing"),
                           schema_name="org.gnome.desktop.peripherals",
                           schema_child_name="touchpad",
                           schema_id="org.gnome.desktop.peripherals.touchpad",
                           key_name="disable-while-typing"),
    ),
  ]

if pointing_stick_is_present():
  _tweaks += [
    TweakPreferencesGroup(_("Pointing Stick"), "pointing-stick",
      PointerSpeedSlider(peripheral_type="pointingstick"),
      PointerAccelProfile(
          title=_("Pointing Stick Acceleration"),
          description=_("Turning acceleration off can allow faster and more precise movements, but can also make the pointing stick more difficult to use."),
          peripheral_type="pointingstick",
      ),
      GSettingsTweakComboRow(
          title=_("Scroll Method"),
          schema_name="org.gnome.desktop.peripherals",
          schema_child_name="pointingstick",
          schema_id="org.gnome.desktop.peripherals.pointingstick",
          key_name="scroll-method",
      ),
    ),
  ]

TWEAK_GROUP = TweakPreferencesPage("mouse", _("Mouse & Touchpad"), *_tweaks)