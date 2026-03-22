# Copyright (c) 2011 John Stowers
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import os
import os.path
import logging
import zipfile
import tempfile
import json
import gettext
import subprocess

from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Gio
from gi.repository import GdkPixbuf
from gi.repository import Gdk
from gtweak.tweakmodel import Tweak

from gtweak.utils import walk_directories, make_combo_list_with_default, extract_zip_file, get_resource_dirs
from gtweak.gshellwrapper import GnomeShellFactory
from gtweak.gtksettings import GtkSettingsManager
from gtweak.gsettings import GSettingsMissingError
from gtweak.widgets import (TweakPreferencesPage, GSettingsTweakComboRow,TweakPreferencesGroup, GSettingsFileChooserButtonTweak, FileChooserButton, build_label_beside_widget)

# Set up translation function
try:
    # Try to use the system-wide gettext if available
    _
except NameError:
    # Fallback: define a simple translation function
    def _(msg):
        return msg


_shell = GnomeShellFactory().get_shell()
_shell_loaded = _shell is not None

# Color definitions for accent color swatches
_ACCENT_COLORS = {
    "blue": "#1e90ff",
    "teal": "#20b2aa",
    "green": "#4caf50",
    "yellow": "#ffc107",
    "orange": "#ff9800",
    "red": "#f44336", 
    "pink": "#e91e63",
    "purple": "#9c27b0",
    "slate": "#607d8b",
    "brown": "#795548",
}

class AccentColorGrid(Gtk.Box, Tweak):
    """Widget for displaying accent color swatches"""
    def __init__(self, title, description="", **options):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=6)
        Tweak.__init__(self, title=title, description=description, **options)
        
        try:
            self._settings = Gio.Settings.new("org.gnome.desktop.interface")
            self._current_color = self._settings.get_string("accent-color")
            self._settings.connect("changed::accent-color", self._on_settings_changed)
        except:
            self._current_color = "blue"
            self._settings = None
        
        # CSS provider for swatch border styling
        self._swatch_css_provider = Gtk.CssProvider()
        self._swatch_css_provider.load_from_data(b"""
            .color-swatch-frame {
                border: 3px solid @accent_color;
            }
        """)
        
        # Create color swatch grid
        flow_box = Gtk.FlowBox()
        flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
        flow_box.set_max_children_per_line(10)
        flow_box.set_column_spacing(6)
        flow_box.set_row_spacing(6)
        flow_box.connect("child-activated", self._on_color_selected)
        
        # Store color mapping and swatches for updating
        self._color_swatches = {}
        self._swatches_by_name = {}
        self._swatch_frames = {}
        self._current_selected_frame = None
        
        # Add color swatches
        for color_name, hex_color in _ACCENT_COLORS.items():
            # Create frame for each swatch
            frame = Gtk.Frame()
            frame.set_size_request(40, 40)
            
            swatch = Gtk.DrawingArea()
            swatch.set_size_request(40, 40)
            
            # Store color name and hex on the widget
            swatch.color_name = color_name
            swatch.hex_color = hex_color
            
            # Create draw function with proper closure using factory
            swatch.set_draw_func(self._make_draw_func(color_name, hex_color))
            
            frame.set_child(swatch)
            
            # Append to flow box (returns None in GTK4)
            flow_box.append(frame)
            self._color_swatches[frame] = color_name
            self._swatches_by_name[color_name] = frame
            self._swatch_frames[color_name] = frame
        
        self.append(flow_box)
        self._flow_box = flow_box
        self.widget_for_size_group = None
        
        # Apply initial border to current color
        self._update_swatch_border()
    
    def _make_draw_func(self, color_name, hex_color):
        """Factory function to create a draw function with proper closure"""
        def draw_circle(area, ctx, width, height):
            r, g, b = self._hex_to_rgb(hex_color)
            
            # Draw filled circle (centered in the available space)
            ctx.set_source_rgb(r, g, b)
            ctx.arc(width / 2, height / 2, 14, 0, 2 * 3.14159)
            ctx.fill()
        
        return draw_circle
    
    def _hex_to_rgb(self, hex_color):
        """Convert hex color to RGB tuple (0-1 range)"""
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16)/255.0 for i in (0, 2, 4))
        return (r, g, b)
    
    def _on_color_selected(self, flow_box, child):
        """Handle color selection"""
        # child is FlowBoxChild, get the frame widget inside it
        frame = child.get_child()
        if frame and isinstance(frame, Gtk.Frame):
            # Get the swatch (DrawingArea) from inside the frame
            swatch = frame.get_child()
            if swatch and hasattr(swatch, 'color_name'):
                if self._settings:
                    try:
                        self._settings.set_string("accent-color", swatch.color_name)
                    except Exception as e:
                        logging.error(f"Failed to set accent color: {e}")
    
    def _on_settings_changed(self, settings, key):
        """Handle settings changes to update visual selection"""
        if key == "accent-color":
            self._current_color = settings.get_string(key)
            # Update CSS border to reflect new selection
            self._update_swatch_border()
    
    def _update_swatch_border(self):
        """Update CSS border on currently selected swatch"""
        # Remove border from previous selection
        if self._current_selected_frame:
            self._current_selected_frame.get_style_context().remove_provider(self._swatch_css_provider)
        
        # Add border to current selection
        if self._current_color in self._swatch_frames:
            frame = self._swatch_frames[self._current_color]
            frame.add_css_class("color-swatch-frame")
            style_context = frame.get_style_context()
            style_context.add_provider(self._swatch_css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self._current_selected_frame = frame


class GtkThemeSwitcher(GSettingsTweakComboRow):
    def __init__(self, **options):
        self._gtksettings3 = GtkSettingsManager('3.0')
        self._gtksettings4 = GtkSettingsManager('4.0')

        GSettingsTweakComboRow.__init__(self,
			_("Legacy Applications"),
            "org.gnome.desktop.interface",
            "gtk-theme",
            make_combo_list_with_default(self._get_valid_themes(), "Adwaita"),
            **options)


    def _get_valid_themes(self):
        """ Only shows themes that have variations for gtk3"""
        gtk_ver = Gtk.MINOR_VERSION
        if gtk_ver % 2: # Want even number
            gtk_ver += 1

        valid = ['Adwaita', 'HighContrast', 'HighContrastInverse']
        valid += walk_directories(get_resource_dirs("themes"), lambda d:
                    os.path.exists(os.path.join(d, "gtk-3.0", "gtk.css")) or \
                         os.path.exists(os.path.join(d, "gtk-3.{}".format(gtk_ver))))
        return set(valid)

    def _on_combo_changed(self, combo, _):
        item = combo.get_selected_item()
        if item:
            value = item.value
            self.settings.set_string(self.key_name, value)
        # Turn off Global Dark Theme when theme is changed.
        # https://bugzilla.gnome.org/783666
        try:
            self._gtksettings3.set_integer("gtk-application-prefer-dark-theme",
                                          0)
            self._gtksettings4.set_integer("gtk-application-prefer-dark-theme",
                                          0)
        except:
            self.notify_information(_("Error writing setting"))


class IconThemeSwitcher(GSettingsTweakComboRow):
    def __init__(self, **options):
        GSettingsTweakComboRow.__init__(self,
			_("Icons"),
			"org.gnome.desktop.interface",
            "icon-theme",
            make_combo_list_with_default(self._get_valid_icon_themes(), "Adwaita"),
            **options)

    def _get_valid_icon_themes(self):
        valid = walk_directories(get_resource_dirs("icons"), lambda d:
                    os.path.isdir(d) and \
			os.path.exists(os.path.join(d, "index.theme")))
        return set(valid)

class CursorThemeSwitcher(GSettingsTweakComboRow):
    def __init__(self, **options):
        GSettingsTweakComboRow.__init__(self,
			_("Cursor"),
            "org.gnome.desktop.interface",
            "cursor-theme",
            make_combo_list_with_default(self._get_valid_cursor_themes(), "Adwaita"),
            **options)

    def _get_valid_cursor_themes(self):
        valid = walk_directories(get_resource_dirs("icons"), lambda d:
                    os.path.isdir(d) and \
                        os.path.exists(os.path.join(d, "cursors")))
        return set(valid)

class ShellThemeTweak(GSettingsTweakComboRow):
    THEME_EXT_NAME = "user-theme@gnome-shell-extensions.gcampax.github.com"
    THEME_GSETTINGS_SCHEMA = "org.gnome.shell.extensions.user-theme"
    THEME_GSETTINGS_NAME = "name"
    THEME_GSETTINGS_DIR = os.path.join(GLib.get_user_data_dir(), "gnome-shell", "extensions",
                                       THEME_EXT_NAME, "schemas")
    LEGACY_THEME_DIR = os.path.join(GLib.get_home_dir(), ".themes")
    THEME_DIR = os.path.join(GLib.get_user_data_dir(), "themes")

    def __init__(self):
        #check the shell is running and the usertheme extension is present
        error = _("Unknown error")
        self._shell = _shell

        if self._shell is None:
            logging.warning("Shell not running", exc_info=True)
            error = _("Shell not running")
        else:
            try:
                extensions = self._shell.list_extensions()
                if ShellThemeTweak.THEME_EXT_NAME in extensions and extensions[ShellThemeTweak.THEME_EXT_NAME]["state"] == 1:
                    error = None

                else:
                    error = _("Shell user-theme extension not enabled")
            except Exception as e:
                logging.warning("Could not list shell extensions", exc_info=True)
                error = _("Could not list shell extensions")

        if error:
            valid = []
        else:
            #include both system, and user themes
            #note: the default theme lives in /system/data/dir/gnome-shell/theme
            #      and not themes/, so add it manually later
            dirs = [os.path.join(d, "themes") for d in GLib.get_system_data_dirs()]
            dirs += [ShellThemeTweak.THEME_DIR]
            dirs += [ShellThemeTweak.LEGACY_THEME_DIR]
            # add default theme directory since some alternative themes are installed here
            dirs += [os.path.join(d, "gnome-shell", "theme") for d in GLib.get_system_data_dirs()]

            valid = walk_directories(dirs, lambda d:
                    os.path.exists(os.path.join(d, "gnome-shell.css")) or \
                    (
                        os.path.exists(os.path.join(d, "gnome-shell")) and \
                        os.path.exists(os.path.join(d, "gnome-shell", "gnome-shell.css"))
                    ))
            #the default value to reset the shell is an empty string
            valid.extend( ("",) )
            valid = set(valid)
        
        # load the schema from the user installation of User Themes if it exists
        schema_dir = ShellThemeTweak.THEME_GSETTINGS_DIR if os.path.exists(ShellThemeTweak.THEME_GSETTINGS_DIR) else None

        # build a combo box with all the valid theme options
        GSettingsTweakComboRow.__init__(self,
		  title=_("Shell"),
          subtitle=error if error else None,
          schema_name=ShellThemeTweak.THEME_GSETTINGS_SCHEMA,
          schema_dir=schema_dir,
          key_name=ShellThemeTweak.THEME_GSETTINGS_NAME,
          key_options=make_combo_list_with_default(opts=list(valid), default="", default_text=_("Adwaita (default)")),
          loaded=_shell_loaded,
        )

class ShellThemeInstallerTweak(Gtk.Box, Tweak):
    def __init__(self, title, description=None, **options):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.HORIZONTAL)
        Tweak.__init__(self, title=title, description=description, **options)

        chooser = FileChooserButton(
                    _("Select a theme"),
                    ["application/zip"])
        chooser.connect("notify::file-uri", self._on_file_set)

        build_label_beside_widget(title, chooser, hbox=self)

        self.widget_for_size_group = None

    def _on_file_set(self, chooser: FileChooserButton, _pspec):
        f = chooser.get_absolute_path()

        if not f:
            return

        with zipfile.ZipFile(f, 'r') as z:
            try:
                fragment = ()
                theme_name = None
                for n in z.namelist():
                    if n.endswith("gnome-shell.css"):
                        fragment = n.split("/")[0:-1]
                    if n.endswith("gnome-shell/theme.json"):
                        logging.info("New style theme detected (theme.json)")
                        #new style theme - extract the name from the json file
                        tmp = tempfile.mkdtemp()
                        z.extract(n, tmp)
                        with open(os.path.join(tmp,n)) as f:
                            try:
                                theme_name = json.load(f)["shell-theme"]["name"]
                            except:
                                logging.warning("Invalid theme format", exc_info=True)

                if not fragment:
                    raise Exception("Could not find gnome-shell.css")

                if not theme_name:
                    logging.info("Old style theme detected (missing theme.json)")
                    #old style themes name was taken from the zip name
                    if fragment[0] == "theme" and len(fragment) == 1:
                        theme_name = os.path.basename(f)
                    else:
                        theme_name = fragment[0]

                theme_members_path = "/".join(fragment)

                ok, updated = extract_zip_file(
                                z,
                                theme_members_path,
                                os.path.join(ShellThemeTweak.THEME_DIR, theme_name, "gnome-shell"))

                if ok:
                    if updated:
                        self.notify_information(_("%s theme updated successfully") % theme_name)
                    else:
                        self.notify_information(_("%s theme installed successfully") % theme_name)
                else:
                    self.notify_information(_("Error installing theme"))


            except:
                # does not look like a valid theme
                self.notify_information(_("Invalid theme"))
                logging.warning("Error parsing theme zip", exc_info=True)

        # set button back to default state
        chooser.props.file_uri = None


class ColorSchemeSwitcher(GSettingsTweakComboRow):
    """Switcher for system color scheme (Light/Dark mode)"""
    def __init__(self, **options):
        try:
            # Check if color-scheme is supported first
            settings = Gio.Settings.new("org.gnome.desktop.interface")
            schema = settings.get_property("settings-schema")
            has_color_scheme = schema and "color-scheme" in schema.list_keys()
            
            if not has_color_scheme:
                raise Exception("color-scheme key not available in schema")
            
            # If supported, let the schema provide the valid values automatically
            # by passing None for key_options. This ensures we use the exact
            # enum values defined in the schema rather than hardcoding them.
            GSettingsTweakComboRow.__init__(self,
                title=_("Style"),
                schema_name="org.gnome.desktop.interface",
                key_name="color-scheme",
                key_options=None,  # Let schema provide valid enum values
                **options)
        except Exception as e:
            logging.debug(f"Color scheme not supported: {e}")
            raise

    def _check_color_scheme_support(self):
        """Check if color-scheme key is available"""
        try:
            settings = Gio.Settings.new("org.gnome.desktop.interface")
            schema = settings.get_property("settings-schema")
            if schema:
                return "color-scheme" in schema.list_keys()
            return False
        except Exception as e:
            logging.debug(f"Color scheme not supported: {e}")
            return False


class BackgroundPreviewWidget(Gtk.Box, Tweak):
    """Widget for displaying background image previews"""
    
    PREVIEW_WIDTH = 320
    PREVIEW_HEIGHT = 180
    
    def __init__(self, **options):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=12)
        Tweak.__init__(self, title=_("Preview"), description="", **options)
        
        # Prevent vertical expansion
        self.set_vexpand(False)
        self.set_valign(Gtk.Align.START)
        
        # Get actual monitor aspect ratio
        try:
            display = Gdk.Display.get_default()
            monitors = display.get_monitors()
            if len(monitors) > 0:
                monitor = monitors.get_item(0)
                geometry = monitor.get_geometry()
                aspect_ratio = geometry.width / geometry.height
            else:
                aspect_ratio = 16 / 9  # fallback
        except Exception as e:
            logging.debug(f"Could not get monitor aspect ratio: {e}")
            aspect_ratio = 16 / 9  # fallback
        
        try:
            self._settings = Gio.Settings.new("org.gnome.desktop.background")
            self._settings.connect("changed::picture-uri", self._on_background_changed)
            self._settings.connect("changed::picture-uri-dark", self._on_background_changed)
            self._settings.connect("changed::picture-options", self._on_picture_options_changed)
            self._picture_options = self._settings.get_string("picture-options")
        except Exception as e:
            logging.warning(f"Failed to initialize background settings: {e}")
            self._settings = None
            self._picture_options = "scaled"
        
        # Try to also monitor color-scheme for visual feedback
        try:
            self._interface_settings = Gio.Settings.new("org.gnome.desktop.interface")
            self._interface_settings.connect("changed::color-scheme", self._on_style_changed)
            self._current_style = self._interface_settings.get_string("color-scheme")
        except Exception as e:
            logging.debug(f"Color scheme not available: {e}")
            self._interface_settings = None
            self._current_style = "prefer-light"
        
        # CSS provider for frame highlighting
        self._frame_css_provider = Gtk.CssProvider()
        self._frame_css_provider.load_from_data(b"""
            frame {
                border: 3px solid @accent_color;
            }
        """)
        
        # CSS provider for label styling (always applied)
        self._label_css_provider = Gtk.CssProvider()
        css_data = f"""
            .light-theme-frame {{
                background-color: #f5f5f5;
                color: #000000;
                aspect-ratio: {aspect_ratio};
            }}
            .light-theme-label {{
                background-color: #f5f5f5;
                color: #000000;
                padding: 4px 8px;
                border-radius: 4px;
            }}
            .dark-theme-frame {{
                background-color: #1a1a1a;
                color: #ffffff;
                aspect-ratio: {aspect_ratio};
            }}
            .dark-theme-label {{
                background-color: #1a1a1a;
                color: #ffffff;
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """.encode('utf-8')
        self._label_css_provider.load_from_data(css_data)
        
        # Create preview container
        preview_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        preview_box.set_homogeneous(True)
        
        # Wrap in a container to maintain fixed height
        preview_wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        preview_wrapper.set_vexpand(False)
        preview_wrapper.set_size_request(-1, self.PREVIEW_HEIGHT + 60)  # Fixed height for preview + label
        preview_wrapper.append(preview_box)
        
        # Apply label CSS provider to preview box so labels are always styled
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self._label_css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        # Light theme preview
        light_frame = Gtk.Frame()
        light_frame.add_css_class("light-theme-frame")
        light_frame.set_label_align(0.0)
        light_frame.set_vexpand(False)
        light_frame.set_valign(Gtk.Align.START)
        light_label = Gtk.Label(label=_("Light"))
        light_label.add_css_class("light-theme-label")
        light_frame.set_label_widget(light_label)
        self._light_image = Gtk.Picture()
        self._light_image.set_size_request(self.PREVIEW_WIDTH, self.PREVIEW_HEIGHT)
        self._light_image.set_vexpand(False)
        self._light_image.set_valign(Gtk.Align.START)
        self._apply_picture_options_fit(self._light_image)
        light_frame.set_child(self._light_image)
        self._light_frame = light_frame
        
        # Make light image clickable
        light_gesture = Gtk.GestureClick.new()
        light_gesture.connect("released", self._on_light_preview_clicked)
        self._light_image.add_controller(light_gesture)
        
        # Add cursor feedback
        light_event_controller = Gtk.EventControllerMotion.new()
        light_event_controller.connect("enter", lambda *args: self._set_cursor_pointer(self._light_image))
        light_event_controller.connect("leave", lambda *args: self._reset_cursor(self._light_image))
        self._light_image.add_controller(light_event_controller)
        
        preview_box.append(light_frame)
        
        # Dark theme preview
        dark_frame = Gtk.Frame()
        dark_frame.add_css_class("dark-theme-frame")
        dark_frame.set_label_align(0.0)
        dark_label = Gtk.Label(label=_("Dark"))
        dark_label.add_css_class("dark-theme-label")
        dark_frame.set_label_widget(dark_label)
        self._dark_image = Gtk.Picture()
        self._dark_image.set_size_request(self.PREVIEW_WIDTH, self.PREVIEW_HEIGHT)
        self._apply_picture_options_fit(self._dark_image)
        dark_frame.set_child(self._dark_image)
        self._dark_frame = dark_frame
        
        # Make dark image clickable
        dark_gesture = Gtk.GestureClick.new()
        dark_gesture.connect("released", self._on_dark_preview_clicked)
        self._dark_image.add_controller(dark_gesture)
        
        # Add cursor feedback
        dark_event_controller = Gtk.EventControllerMotion.new()
        dark_event_controller.connect("enter", lambda *args: self._set_cursor_pointer(self._dark_image))
        dark_event_controller.connect("leave", lambda *args: self._reset_cursor(self._dark_image))
        self._dark_image.add_controller(dark_event_controller)
        
        preview_box.append(dark_frame)
        
        self.append(preview_wrapper)
        
        self.widget_for_size_group = None
        
        # Initial load
        self._update_previews()
        self._update_frame_styling()
    
    def _on_background_changed(self, settings, key):
        """Handle background settings changes"""
        self._update_previews()
    
    def _on_style_changed(self, settings, key):
        """Handle color-scheme changes"""
        if key == "color-scheme":
            self._current_style = settings.get_string(key)
            self._update_frame_styling()
    
    def _on_picture_options_changed(self, settings, key):
        """Handle picture-options changes"""
        if key == "picture-options":
            self._picture_options = settings.get_string(key)
            self._apply_picture_options_fit(self._light_image)
            self._apply_picture_options_fit(self._dark_image)
    
    def _apply_picture_options_fit(self, picture_widget):
        """Apply the appropriate ContentFit based on picture-options setting"""
        # Map picture-options values to GTK ContentFit values
        options_map = {
            "none": Gtk.ContentFit.FILL,  # No scaling
            "centered": Gtk.ContentFit.CONTAIN,  # Center without stretching
            "scaled": Gtk.ContentFit.CONTAIN,  # Scale to fit
            "stretched": Gtk.ContentFit.FILL,  # Stretch to fill
            "zoom": Gtk.ContentFit.COVER,  # Zoom to cover
            "spanned": Gtk.ContentFit.COVER,  # Spanned across monitors
        }
        
        fit = options_map.get(self._picture_options, Gtk.ContentFit.COVER)
        picture_widget.set_content_fit(fit)
    
    def _on_light_preview_clicked(self, gesture, n_press, x, y):
        """Handle click on light preview - set to light style"""
        if self._interface_settings:
            try:
                self._interface_settings.set_string("color-scheme", "prefer-light")
                logging.info("Background preview: Switched to light style")
            except Exception as e:
                logging.warning(f"Failed to set light style: {e}")
    
    def _on_dark_preview_clicked(self, gesture, n_press, x, y):
        """Handle click on dark preview - set to dark style"""
        if self._interface_settings:
            try:
                self._interface_settings.set_string("color-scheme", "prefer-dark")
                logging.info("Background preview: Switched to dark style")
            except Exception as e:
                logging.warning(f"Failed to set dark style: {e}")
    
    def _set_cursor_pointer(self, widget):
        """Set cursor to pointer to show widget is clickable"""
        try:
            cursor = Gdk.Cursor.new_from_name("pointer", None)
            widget.set_cursor(cursor)
        except Exception as e:
            logging.debug(f"Could not set cursor: {e}")
    
    def _reset_cursor(self, widget):
        """Reset cursor to default"""
        try:
            widget.set_cursor(None)
        except Exception as e:
            logging.debug(f"Could not reset cursor: {e}")
    
    def _update_frame_styling(self):
        """Update CSS styling to highlight the current style"""
        try:
            # Add CSS for selected state based on current style
            if self._current_style == "prefer-light":
                self._light_frame.get_style_context().add_provider(
                    self._frame_css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
                self._dark_frame.get_style_context().remove_provider(
                    self._frame_css_provider
                )
                    
            elif self._current_style == "prefer-dark":
                self._dark_frame.get_style_context().add_provider(
                    self._frame_css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
                self._light_frame.get_style_context().remove_provider(
                    self._frame_css_provider
                )
        except Exception as e:
            logging.debug(f"Could not update frame styling: {e}")
    
    def _update_previews(self):
        """Update both background previews"""
        if not self._settings:
            return
        
        try:
            # Get current URIs
            light_uri = self._settings.get_string("picture-uri")
            dark_uri = self._settings.get_string("picture-uri-dark")
            
            # Update previews
            self._load_image_preview(self._light_image, light_uri)
            self._load_image_preview(self._dark_image, dark_uri)
        except Exception as e:
            logging.error(f"Error updating background previews: {e}", exc_info=True)
    
    def _load_image_preview(self, picture_widget, uri):
        """Load and display image preview from URI
        
        This uses Gio's portal-aware async loading which properly handles
        both local filesystem access and Flatpak sandbox restrictions
        automatically without needing fallbacks.
        """
        if not uri or uri == "":
            picture_widget.set_paintable(None)
            return
        
        try:
            file = Gio.File.new_for_uri(uri)
            
            def on_image_loaded(source_file, result, user_data=None):
                try:
                    # Try to get file contents
                    try:
                        success, contents, etag = source_file.load_contents_finish(result)
                        if not success or not contents:
                            logging.warning(f"Background: Async load failed (success={success})")
                            picture_widget.set_paintable(None)
                            return
                    except TypeError:
                        # Older GIO version returns just contents
                        contents = source_file.load_contents_finish(result)
                        if not contents:
                            logging.warning(f"Background: Async load returned no contents")
                            picture_widget.set_paintable(None)
                            return
                    
                    if not contents:
                        logging.warning(f"Background: Async load got empty contents")
                        picture_widget.set_paintable(None)
                        return
                    
                    logging.warning(f"Background: Loaded {len(contents)} bytes asynchronously")
                    # Use stream-based loading for auto format detection (works for PNG and JPEG)
                    input_stream = Gio.MemoryInputStream.new_from_bytes(
                        GLib.Bytes.new(contents)
                    )
                    pixbuf = GdkPixbuf.Pixbuf.new_from_stream(input_stream, None)
                    scaled_pixbuf = self._scale_pixbuf(pixbuf)
                    texture = Gdk.Texture.new_for_pixbuf(scaled_pixbuf)
                    picture_widget.set_paintable(texture)
                    logging.warning(f"Background: Preview rendered successfully")
                        
                except Exception as e:
                    logging.warning(f"Background: Error loading image: {type(e).__name__}: {e}")
                    picture_widget.set_paintable(None)
            
            logging.warning(f"Background: Loading from {uri}")
            cancellation = Gio.Cancellable.new()
            file.load_contents_async(cancellation, on_image_loaded, None)
        except Exception as e:
            logging.error(f"Background: Failed to start load: {type(e).__name__}: {e}")
            picture_widget.set_paintable(None)
    
    def _scale_pixbuf(self, pixbuf):
        """Scale pixbuf to fit preview size while maintaining aspect ratio"""
        original_width = pixbuf.get_width()
        original_height = pixbuf.get_height()
        
        # Calculate scaling to fit within PREVIEW_WIDTH x PREVIEW_HEIGHT
        scale_w = self.PREVIEW_WIDTH / original_width
        scale_h = self.PREVIEW_HEIGHT / original_height
        scale = min(scale_w, scale_h)
        
        new_width = int(original_width * scale)
        new_height = int(original_height * scale)
        
        return pixbuf.scale_simple(new_width, new_height, 
                                   GdkPixbuf.InterpType.BILINEAR)



# Build the appearance tweaks, with graceful handling of unsupported features
_styles_tweaks = []

# Always add the core theme switchers
_styles_tweaks.extend([
    CursorThemeSwitcher(),
    IconThemeSwitcher(),
    ShellThemeTweak(),
    GtkThemeSwitcher(),
])


TWEAK_GROUP = TweakPreferencesPage("appearance", _("Appearance"),
  TweakPreferencesGroup(
    _("Background"), "title-backgrounds",
    BackgroundPreviewWidget(),
    GSettingsFileChooserButtonTweak(
      _("Default Image"),
      "org.gnome.desktop.background",
      "picture-uri",
      mimetypes=["application/xml", "image/png", "image/jpeg"],
    ),
    GSettingsFileChooserButtonTweak(
      _("Dark Style Image"),
      "org.gnome.desktop.background",
      "picture-uri-dark",
      mimetypes=["application/xml", "image/png", "image/jpeg"],
    ),
    GSettingsTweakComboRow(
      _("Adjustment"), "org.gnome.desktop.background", "picture-options"
    ),
   ),
    TweakPreferencesGroup(
    _("Accent Color"), "title-accent",
    AccentColorGrid(_("Accent Color"), _("Choose system accent color"))
  ),
   TweakPreferencesGroup( _("Styles"), "title-styles",
    *_styles_tweaks
  ),
)
