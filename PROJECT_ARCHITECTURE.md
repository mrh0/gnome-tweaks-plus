# GNOME Tweaks Architecture & Design Documentation

## Project Overview

GNOME Tweaks is a advanced settings application for GNOME Desktop Environment. It provides access to system tweaks that aren't exposed in the standard GNOME Settings application. This codebase serves as a foundation for building a fully-fledged replacement for GNOME Settings.

**Version:** 49.0  
**Package ID:** `org.gnome.tweaks`  
**License:** GPL-3.0+  
**Language:** Python 3.10+  
**Build System:** Meson  

## Technology Stack

### Core Dependencies

- **GTK 4 (≥ 4.10.0)** - Main UI framework, modern declarative UI toolkit
- **libadwaita 1 (≥ 1.4.0)** - GNOME's Adwaita design system library for GTK 4
- **GLib 2.0 (≥ 2.78.0)** - Core utilities and event loop
- **PyGObject 3.0 (≥ 3.46.0)** - Python bindings for GObject/GTK
- **gsettings-desktop-schemas (≥ 46.0)** - System-wide GSettings schemas for desktop
- **libgudev 1.0 (≥ 238)** - Device management library
- **gnome-desktop 4.0** - GNOME desktop integration
- **libnotify** - Desktop notifications
- **Pango** - Text rendering and internationalization

**Optional/Audio Dependencies:**
- **pulsectl** - PulseAudio/PipeWire control (pip/package manager install)
- **sound-theme-freedesktop** - Sound theme resources

### Runtime Environment

- Python 3 with GObject Introspection (GIR)
- D-Bus communication (via GIO)
- GSettings configuration system
- GNOME Shell integration layer

## Project Structure

```
gnome-tweaks-plus/
├── gnome-tweaks                    # Entry point script (shell wrapper)
├── meson.build                     # Main build configuration
├── meson_options.txt               # Build options (profile: default/development)
├── meson-postinstall.py            # Post-install hook (schema compilation)
├── org.gnome.tweaks.json           # Flatpak configuration
├── dconf-override.patch            # dconf schema overrides
│
├── gtweak/                         # Main Python package
│   ├── __init__.py                 # Package initialization
│   ├── app.py                      # GnomeTweaks(Adw.Application) - main app class
│   ├── defs.py.in                  # Template for runtime constants (meson subsitution)
│   ├── tweakmodel.py               # Tweak/TweakGroup data models (GTK ListStore)
│   ├── tweakview.py                # Main Window class and layout
│   ├── widgets.py                  # Reusable widget components
│   ├── gsettings.py                # GSettings schema parsing and access layer
│   ├── gshellwrapper.py            # GNOME Shell D-Bus communication
│   ├── gtksettings.py              # GTK configuration (.ini file) management
│   ├── utils.py                    # Utility functions (notifications, schema reset, etc.)
│   ├── devicemanager.py            # Hardware device detection
│   ├── meson.build                 # Package build config
│   │
│   ├── audio/
│   │   └── audio_manager.py        # Audio system control (PulseAudio/PipeWire)
│   │
│   └── tweaks/                     # Tweak group modules (organized by category)
│       ├── __init__.py
│       ├── tweak_group_appearance.py     # Theme, accent color, dark mode
│       ├── tweak_group_font.py           # Anti-aliasing, font settings
│       ├── tweak_group_keyboard.py       # Keyboard layout, shortcuts, XKB options
│       ├── tweak_group_mouse.py          # Pointer, acceleration, touchpad
│       ├── tweak_group_windows.py        # Window management, focus behavior
│       ├── tweak_group_multitasking.py   # Workspaces, activities
│       ├── tweak_group_sound.py          # Audio device selection, levels
│       └── tweak_group_startup.py        # Autostart applications
│
├── data/                           # Non-code resources
│   ├── meson.build                 # Data build configuration
│   ├── org.gnome.tweaks.desktop.in # Desktop entry (meson template)
│   ├── org.gnome.tweaks.metainfo.xml.in  # AppStream metadata
│   ├── org.gnome.tweaks.service.in # D-Bus service activation file
│   ├── org.gnome.tweaks.gschema.xml # GSettings schema definition
│   ├── tweaks.ui                   # Main UI layout (GTK Builder XML)
│   ├── shell.ui                    # App menu definitions
│   ├── shell.css                   # Theme/styling rules
│   ├── org.gnome.tweaks.svg        # Application icon
│   └── org.gnome.tweaks-symbolic.svg # Symbolic icon variant
│
├── po/                             # Internationalization
│   ├── POTFILES.in                 # List of translatable files
│   ├── LINGUAS                     # List of supported languages
│   ├── *.po                        # Translation files (60+ languages)
│   └── meson.build
│
├── LICENSES/                       # License files
│   ├── GPL-3.0                     # GPL license text
│   └── CC0-1.0                     # Creative Commons attribution
│
├── README.md                       # Project documentation
├── AUTHORS                         # Author information
└── NEWS                            # Changelog
```

## Architectural Patterns

### 1. Application Bootstrap Pattern

**Entry Point Flow:**
```
gnome-tweaks (shell script)
    ↓
Loads gtweak module with environment setup
    ↓
gtweak/__init__.py (package initialization)
    ↓
gtweak.app.GnomeTweaks(Adw.Application)
    ├─ do_startup()  → Setup actions, CSS, signals
    ├─ do_activate() → Create/show main window
    ├─ Model layer   → TweakModel
    └─ View layer    → Window(Adw.ApplicationWindow)
```

**Key File: [gnome-tweaks](gnome-tweaks)**
- Parses command-line arguments (prefix support for uninstalled runs)
- Sets up internationalization (gettext domains)
- Initializes module paths and definitions
- Launches `GnomeTweaks` application

**Key File: [gtweak/app.py](gtweak/app.py#L45)**
- `GnomeTweaks` class extends `Adw.Application`
- Manages application lifecycle (startup, activate)
- Creates main TweakModel and Window
- Handles application-level actions (quit, about, reset)
- Manages extension notice dialog

### 2. Model-View-Controller Architecture

#### Model Layer: [gtweak/tweakmodel.py](gtweak/tweakmodel.py)

```python
Tweak                  # Individual setting/control
    ├─ title: str
    ├─ description: str
    ├─ uid: str (unique identifier)
    ├─ group_name: str (category)
    └─ loaded: bool (conditional loading based on environment)

TweakGroup             # Categorized collection of tweaks
    ├─ name: str (internal identifier)
    ├─ title: str (display name)
    └─ tweaks: List[Tweak]

TweakModel(Gtk.ListStore)  # Data model for sidebar
    ├─ COLUMN_NAME: str (display name)
    ├─ COLUMN_TWEAK: TweakGroup object
    └─ Methods:
        ├─ add_tweak_group()
        ├─ search_matches() → List of matching groups
        └─ Properties: tweaks, tweak_groups
```

**Search Integration:**
- Each Tweak has normalized (`GLib.utf8_casefold`) search cache
- Search cache includes title + description + extra_info
- `search_matches(txt)` performs case-insensitive substring matching

#### View Layer: [gtweak/tweakview.py](gtweak/tweakview.py)

**Window Class Hierarchy:**
```
Adw.ApplicationWindow
    └─ Window (main application window)
        ├─ Decorated with @Gtk.Template (loads tweaks.ui)
        ├─ Header (Adw.HeaderBar with search/menu)
        ├─ Sidebar (Gtk.ListBox - tweak group list)
        ├─ Main Stack (Adw.NavigationView - tweak group content)
        └─ Components:
            ├─ searchbar (Gtk.SearchBar)
            ├─ entry (search text entry)
            ├─ listbox (groups sidebar)
            ├─ main_leaflet (responsive two-pane layout)
            └─ main_stack (individual tweak pages)
```

**UI Layout Pattern:**
- **Responsive Design:** Uses `Adw.Leaflet` for adaptive single/two-pane layout
- **Navigation:** `Adw.NavigationView` for tweak group pages
- **Template-Based:** Window structure defined in GTK Builder XML ([data/tweaks.ui](data/tweaks.ui))
- **CSS Styling:** Applied from [data/shell.css](data/shell.css)

#### Controller Layer: [gtweak/app.py](gtweak/app.py) & Individual Tweaks

- Application actions bridge model and view
- Individual tweaks are self-contained controllers
- Tweaks listen to GSettings changes and update UI
- Tweaks change GSettings and persist changes

### 3. Settings Management Pattern

#### GSettings Integration: [gtweak/gsettings.py](gtweak/gsettings.py)

**Abstraction Layers:**
```
GSettings (system-wide config)
    ↓
_GSettingsSchema (XML parser)
    ├─ Reads .gschema.xml files
    ├─ Translates schema descriptions
    └─ Validates available keys
    ↓
GSettingsSetting (abstraction)
    ├─ Wraps Gio.Settings object
    ├─ Type conversion and validation
    └─ Change signal forwarding
    ↓
GSettings*Tweak subclasses (widgets)
    ├─ GSettingsTweakSwitchRow
    ├─ GSettingsTweakComboRow
    └─ GSettingsFileChooserButtonTweak
```

**Key Patterns:**
- Schema validation with fallback paths
- Supports relocatable schemas (portable schema instances)
- Change notification via GSettings::changed signal
- Automatic UI-to-settings synchronization via GObject property binding

#### GTK Settings: [gtweak/gtksettings.py](gtweak/gtksettings.py)

- Manages `~/.config/gtk-{version}/settings.ini` files
- Handles GTK version-specific settings
- Direct KeyFile manipulation (not GSettings-based)

### 4. Tweak Module Pattern

Each tweak group is an independent Python module in [gtweak/tweaks/](gtweak/tweaks/):

**Module Structure Example (tweak_group_mouse.py):**
```python
# Classes (custom Tweak subclasses as needed)
class KeyThemeSwitcher(GSettingsSwitchTweakValue):
    def get_active(self): return self.settings.get_string()
    def set_active(self, v): self.settings.set_string()

class PointerAccelProfile(GSettingsSwitchTweakValue):
    # Custom logic for enum-to-bool conversion
    pass

# Factory function
TWEAK_GROUP = TweakGroup(
    name="mouse",
    title=_("Mouse"),
    KeyThemeSwitcher(...),
    PointerAccelProfile(...),
    # ... more tweaks
)
```

**Tweak Loading Mechanism:**
- Modules imported dynamically in [gtweak/tweakview.py](gtweak/tweakview.py)
- Each module exports `TWEAK_GROUP` constant
- Groups added to TweakModel in order
- Individual tweaks can be conditionally loaded based on:
  - `loaded=True|False` parameter
  - Runtime hardware detection (e.g., touchpad present)
  - GNOME Shell availability

### 5. Widget Abstraction Pattern

**Base Widget Hierarchy: [gtweak/widgets.py](gtweak/widgets.py)**

```
Gtk.Widget (GTK 4 base)
    │
    ├─ GSettingsSwitchRow (Adw.SwitchRow)
    │   └─ Automatic GSettings↔UI binding
    │
    ├─ GSettingsTweakComboRow (Adw.ComboRow)
    │   └─ Dropdown selection with GSettings backing
    │
    ├─ GSettingsFileChooserButtonTweak
    │   └─ File selection with path storage
    │
└─ TweakPreferencesPage (Adw.PreferencesPage)
    ├─ Container for tweak groups
    ├─ TweakPreferencesGroup (Adw.PreferencesGroup)
    │   └─ Contains individual tweak rows
    │   
    └─ ActionRow subclasses
        ├─ TickActionRow (custom selection indicator)
        ├─ PrimaryButtonSelector (multi-state toggle)
        └─ Custom domain-specific widgets
```

**Widget Factory Pattern:**
- `build_label_beside_widget()` - Combines label with controls
- `build_combo_box_model()` - Creates StringList for ComboBox
- `build_tight_button()` - Zero-padding buttons
- Consistent use of size groups for alignment

### 6. D-Bus/System Integration Pattern

**GNOME Shell Integration: [gtweak/gshellwrapper.py](gtweak/gshellwrapper.py)**

```python
_ShellProxy
    ├─ Bus: org.gnome.Shell
    ├─ Interface 1: org.gnome.Shell (for shell info)
    │   ├─ Mode: "user" | "wayland" | other
    │   └─ ShellVersion: "49.0" (string)
    │
    └─ Interface 2: org.gnome.Shell.Extensions (for extensions)
        ├─ Get available extensions
        ├─ Manage extension state
        └─ Extension metadata queries
```

**Singleton Pattern:**
```python
GnomeShellFactory.get_shell()  # Returns None if shell unavailable
```

**Device Management: [gtweak/devicemanager.py](gtweak/devicemanager.py)**

- Uses libgudev (GUdev) for hardware enumeration
- Detects: touchpad presence, input devices, etc.
- Used for conditional tweak loading

### 7. Internationalization Pattern

**Setup: [gnome-tweaks](gnome-tweaks)**

```python
set_internationalization(domain="gnome-tweaks", locale_dir=LOCALE_DIR)
gettext.install(domain, names=('gettext', 'ngettext'))  # Enables _() and ngettext()
```

**Translation Coverage:**
- Strings wrapped in `_("string")` for translation
- 60+ language translations in [po/](po/)
- Translation system works with schema descriptions from XML
- GSettings schema translations loaded automatically

**Key Functions:**
```python
gettext(tweakgroup_name)        # Fetch localized group name
xkb_info.description_for_group()  # Get translated descriptions
```

## UI Layout & Design

### Main Window Composition [data/tweaks.ui](data/tweaks.ui)

```
Adw.ApplicationWindow
│
├─ main_box (Gtk.Box, vertical)
│  │
│  ├─ header (Adw.Leaflet - responsive)
│  │  ├─ left_header (Adw.HeaderBar)
│  │  │  ├─ search_btn (Gtk.ToggleButton)
│  │  │  └─ title_widget (Adw.WindowTitle)
│  │  │
│  │  └─ right_header (Adw.HeaderBar)
│  │
│  └─ main_leaflet (Adw.Leaflet - responsive two-pane layout)
│     ├─ left_box
│     │  ├─ searchbar (Gtk.SearchBar)
│     │  │  └─ entry (Gtk.SearchEntry)
│     │  │
│     │  └─ listbox (Gtk.ListBox)
│     │     └─ Rows (group headers, populated from model)
│     │
│     └─ right_box
│        └─ main_content_scroll (Gtk.ScrolledWindow)
│           └─ main_stack (Adw.NavigationView)
│              └─ Pages (individual tweak group views)
```

**Responsive Behavior:**
- On narrow screens: Single column, groups in sidebar (collapsed), click to expand
- On wide screens: Two panels - sidebar + content

**Search Behavior:**
- Shows search bar to filter groups and tweaks
- Real-time filtering as user types
- Shows only groups containing matching tweaks

### Visual Design System

**Adwaita Design Language:**
- Modern flat design
- HIG-compliant spacing and sizing
- Accent color support (GNOME 43+)
- Light/dark theme aware

**CSS Customization: [data/shell.css](data/shell.css)**
- Tweak titlebar customization
- Custom style classes applied to widgets
- Integrated with GTK's color/theme system

**Icon Theme:**
- Symbolic icons (monochrome, scalable)
- References from `GtkIconTheme` (system icons, Flatpak paths)
- Application icon: [data/org.gnome.tweaks.svg](data/org.gnome.tweaks.svg)

### Metadata & Integration

**Desktop Entry: [data/org.gnome.tweaks.desktop.in](data/org.gnome.tweaks.desktop.in)**
- Application launcher definition
- Categories, keywords, screen reader text
- I18n support (translated name/description)

**AppStream Metadata: [data/org.gnome.tweaks.metainfo.xml.in](data/org.gnome.tweaks.metainfo.xml.in)**
- Software center integration
- Screenshots, release notes
- Feature descriptions

**D-Bus Service: [data/org.gnome.tweaks.service.in](data/org.gnome.tweaks.service.in)**
- System service activation
- Object path and interface definitions
- Executable reference

**GSettings Schema: [data/org.gnome.tweaks.gschema.xml](data/org.gnome.tweaks.gschema.xml)**
- Tweaks application settings (not system tweaks)
- Example: show-extensions-notice boolean flag

## Build & Installation Process

### Meson Build System ([meson.build](meson.build))

**Build Flow:**
```
meson builddir           # Configure build (setup)
ninja -C builddir        # Build (compile if needed, generate resources)
ninja -C builddir install  # Install to prefix
```

**Key Build Targets:**
1. **Data Installation:**
   - Desktop entry → `/share/applications/`
   - Metadata XML → `/share/metainfo/`
   - D-Bus service → `/share/dbus-1/services/`
   - Icons → `/share/icons/hicolor/`
   - Schemas → `/share/glib-2.0/schemas/`
   - CSS/UI files → `/share/gnome-tweaks/`

2. **Python Package Installation:**
   - `gtweak/` → Python site-packages location
   - Meson substitutes template variables `@VAR@` in `.in` files

3. **Post-Install Hooks:**
   - `glib-compile-schemas` - Compile GSettings schemas
   - `gtk-update-icon-cache` - Update icon cache
   - `update-desktop-database` - Update desktop entry database
   - Custom `meson-postinstall.py` script

**Build Options ([meson_options.txt](meson_options.txt)):**
```
--profile=default|development
  (Affects IS_DEVEL flag for conditional behavior)
```

### Version Management

**Version Definition:**
- Declared in `project('gnome-tweaks', version: '49.0')`
- Substituted into [gtweak/defs.py.in](gtweak/defs.py.in) → `VERSION` constant
- Used in about dialog and version display

### Flatpak Integration

**Configuration [org.gnome.tweaks.json](org.gnome.tweaks.json):**
- Runtime: `org.gnome.Sdk` (49)
- Desktop file name prefix: "(Development)" for devel builds
- Extensive filesystem permissions:
  - Icon theme paths
  - Background/pixmap directories
  - GLib schema directories
  - dconf configuration
  - Desktop files (for startup apps)

**Sandbox Features:**
- GPU access (`--device=dri`)
- D-Bus accessibility
- Icon theme environment variables
- Fallback paths for system resources

## Key Runtime Behaviors

### Settings Persistence

1. **GSettings (Most tweaks):**
   - Schema: `org.gnome.oneword.feature`
   - Backed by dconf database
   - User-level (`/home/user/.local/share/dconf/user`)
   - System-level defaults in schema XML

2. **GTK Settings:**
   - File: `~/.config/gtk-3.0/settings.ini` or `gtk-4.0/`
   - INI format key-value pairs
   - Not schema-backed

3. **Application Settings:**
   - Schema: `org.gnome.tweaks`
   - Stores UI state, notification preferences

### Change Notification

- Setup → GSettings schema loaded → Tweaks created and wired
- User changes UI widget → Widget emits "value-changed" signal
- Signal handler calls `settings.set_*()` → dconf writes value
- System components respond to dconf changes (WM, theme engine, etc.)

### Logout/System Notifications

```python
tweak.notify_logout()         # Request logout to apply changes
tweak.notify_information()    # Desktop notification
```

## Extension Architecture (for Creating New Settings Panels)

### Adding a New Tweak

1. **Create tweak in [gtweak/tweaks/](gtweak/tweaks/) module:**

```python
# gtweak/tweaks/tweak_group_myfeature.py
from gtweak.tweakmodel import Tweak, TweakGroup
from gtweak.widgets import GSettingsTweakSwitchRow

class MyFeatureTweak(GSettingsTweakSwitchRow):
    def __init__(self):
        super().__init__(
            title=_("My Feature"),
            description=_("Description"),
            schema_name="org.gnome.desktop.myfeature",
            key_name="enabled"
        )

TWEAK_GROUP = TweakGroup(
    name="myfeature",
    title=_("My Feature"),
    MyFeatureTweak(),
)
```

2. **Register in [gtweak/tweakview.py](gtweak/tweakview.py):**

```python
from gtweak.tweaks.tweak_group_myfeature import TWEAK_GROUP as MyFeatureTweaks

tweaks = [
    # ... existing tweaks
    MyFeatureTweaks
]
```

3. **Ensure GSettings schema available:**
   - Ship `.gschema.xml` file in system path or
   - Ensure dependency provides schema

### Custom Widget Creation

Extend from base classes in [gtweak/widgets.py](gtweak/widgets.py):

```python
class MyCustomTweak(Adw.ActionRow, Tweak):
    def __init__(self):
        Adw.ActionRow.__init__(self)
        Tweak.__init__(self, 
            title=_("Title"),
            description=_("Description")
        )
        
        # Build UI
        self.set_title(self.title)
        
        # Add controls
        switch = Gtk.Switch()
        self.add_suffix(switch)
        
        # Bind to settings
        settings = Gio.Settings.new("org.gnome.desktop.feature")
        settings.bind("key", switch, "active", 
                      Gio.SettingsBindFlags.DEFAULT)
```

## Performance & Optimization Considerations

1. **Lazy Loading:**
   - Schema parsing on-demand when tweak accessed
   - Tweak modules imported only when view shown

2. **Search Optimization:**
   - Normalized search cache built once per tweak
   - String operations cached (not recomputed per keystroke)

3. **GSettings Binding:**
   - Property binding used for automatic sync
   - Avoids manual signal marshalling

4. **UI Threading:**
   - All UI operations on GTK main thread
   - D-Bus calls are blocking (short timeout expectations)

## Future Expansion for GNOME Settings Replacement

To expand this into a full GNOME Settings replacement:

### Architecture Enhancements

1. **Modular Panel System:**
   - Convert tweak groups into independent panel modules
   - Each panel could be a separate process or plugin
   - Central navigation/catalog system

2. **Settings Search:**
   - Full-text indexing of all available settings
   - Fast asynchronous search across all panels
   - Smart suggestions and categorization

3. **Settings Profile/Management:**
   - Export/import settings configurations
   - Safe defaults and rollback provisions
   - Per-user vs system-wide settings

4. **Advanced Validation:**
   - Pre-change validation with warnings
   - Dependency tracking (setting A requires B)
   - Conflict resolution

### UI/UX Improvements

1. **Adaptive UI:**
   - Gesture support (swipe navigation)
   - Touch-friendly controls on small screens
   - Keyboard navigation completeness

2. **Visual Redesign:**
   - Modern card-based layout
   - Grouped related settings with collapsible sections
   - Rich inline help/documentation

3. **Advanced Search:**
   - Fuzzy matching
   - Synonym support ("theme" = "appearance")
   - Setting recommendations based on patterns

### Requirements Scaffolding

The current architecture provides:
- ✅ Settings abstraction (GSettings, GTK settings)
- ✅ UI component library
- ✅ D-Bus integration
- ✅ Notification system
- ✅ Internationalization framework
- ✅ Search and filtering infrastructure
- ✅ Responsive UI layout system
- ✅ Hardware detection (devices)

To-reuse codebase:
- Extract `gtweak/widgets.py` as reusable component library
- Keep `gsettings.py` abstraction for new settings panels
- Adopt Adwaita design patterns for consistency
- Extend TweakModel pattern for new settings categories

## Development Workflow

### Build & Development Cycle

User builds flatpak using gnome-builder

### Adding Translations

1. Mark strings with `_("text")`
2. Run `meson` to regenerate POT template
3. Existing `.po` files updated by translators
4. Compiled at install-time via `glib-compile-schemas`

## Key Code Entry Points for Navigation

| Task | File(s) |
|------|---------|
| Add new tweak | [gtweak/tweaks/tweak_group_*.py](gtweak/tweaks/) |
| Modify main UI | [data/tweaks.ui](data/tweaks.ui), [gtweak/tweakview.py](gtweak/tweakview.py) |
| Add widget | [gtweak/widgets.py](gtweak/widgets.py) |
| Settings integration | [gtweak/gsettings.py](gtweak/gsettings.py) |
| GNOME Shell features | [gtweak/gshellwrapper.py](gtweak/gshellwrapper.py) |
| Hardware detection | [gtweak/devicemanager.py](gtweak/devicemanager.py) |
| Application lifecycle | [gtweak/app.py](gtweak/app.py) |
| Setup/configuration | [gnome-tweaks](gnome-tweaks) |
| Build configuration | [meson.build](meson.build) |

---

**Document Generated:** March 2026  
**Base Project:** GNOME Tweaks 49.0  
**Scope:** Complete architectural analysis for settings application foundation
