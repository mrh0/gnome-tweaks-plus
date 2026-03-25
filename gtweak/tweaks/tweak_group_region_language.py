# Copyright (c) 2011 John Stowers
# Copyright (c) 2026 MRH0
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import subprocess
import logging
from gtweak.widgets import (
    TweakPreferencesPage,
    TweakPreferencesGroup,
    GSettingsTweakComboRow,
    GSettingsTweakSwitchRow,
    build_list_store,
)
import gi
gi.require_version('Adw', '1')
gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gtk, Gio

logger = logging.getLogger(__name__)

# Set up translation function
try:
    _
except NameError:
    def _(msg):
        return msg


def get_available_locales():
    """Get available system locales dynamically from the system.
    
    Matches GNOME Settings cc-region-page.c locale handling.
    Returns a list of tuples: (locale_code, locale_display_name)
    The locale_code is used for LC_TIME and other LC_* categories.
    Examples: ('en_US.UTF-8', 'English (United States)'), ('fr_FR.UTF-8', 'Français (France)')
    """
    try:
        # Get available locales from system (locale -a)
        result = subprocess.run(['locale', '-a'], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            logger.warning("Failed to get system locales")
            return []
        
        locales = []
        seen = set()
        
        for locale_str in result.stdout.strip().split('\n'):
            if not locale_str or not locale_str.strip():
                continue
            
            locale_str = locale_str.strip()
            
            # Normalize encoding to UTF-8 (matches C code approach)
            locale_normalized = locale_str.replace('.utf8', '.UTF-8').replace('.utf-8', '.UTF-8')
            
            # Skip invalid or duplicate locales
            if locale_normalized in seen:
                continue
            if not locale_normalized or locale_normalized == 'C' or locale_normalized == 'POSIX':
                continue
            
            seen.add(locale_normalized)
            
            # Parse locale to create human-readable display name
            # Format: language_COUNTRY.ENCODING[@modifier]
            try:
                # Remove encoding and modifiers
                base_locale = locale_normalized.split('.')[0].split('@')[0]
                
                if '_' in base_locale:
                    lang_code, country_code = base_locale.split('_', 1)
                    # Create readable name: "Language (COUNTRY)"
                    display_name = f"{lang_code.capitalize()} ({country_code.upper()})"
                else:
                    # Only language, no country
                    display_name = base_locale.capitalize()
                
                locales.append((locale_normalized, display_name))
            except Exception as e:
                logger.debug(f"Error parsing locale '{locale_str}': {e}")
                continue
        
        # Sort by display name (matches C code sorting approach)
        locales.sort(key=lambda x: x[1])
        return locales
    
    except subprocess.TimeoutExpired:
        logger.warning("Timeout getting system locales (>5s)")
        return []
    except Exception as e:
        logger.error(f"Error getting available locales: {e}")
        return []


# Build locale options dynamically
_LOCALE_OPTIONS = get_available_locales()

# Default locale used as fallback (matches GNOME Settings DEFAULT_LOCALE)
_DEFAULT_LOCALE = "en_US.UTF-8"


TWEAK_GROUP = TweakPreferencesPage(
    "region-language",
    _("Region & Language"),
    # Format/Region Settings (affects LC_TIME, LC_NUMERIC, LC_MONETARY, LC_MEASUREMENT, LC_PAPER)
    # This controls how dates, times, numbers, and currencies are displayed
    # Based on: gnome-control-center/cc-region-page.c
    TweakPreferencesGroup(
        _("Formats"),
        "formats-region",
        # Region/Locale setting for user formatting preferences
        # This is stored in org.gnome.system.locale > region and affects LC_* environment variables
        GSettingsTweakComboRow(
            _("Region"),
            "org.gnome.system.locale",
            "region",
            key_options=_LOCALE_OPTIONS if _LOCALE_OPTIONS else ((_("English (United States)"), _DEFAULT_LOCALE),)
        ) if _LOCALE_OPTIONS else None,
    ) if _LOCALE_OPTIONS else None,
    # Date and Time Display Settings
    TweakPreferencesGroup(
        _("Time &amp; Date Display"),
        "time-date-display",
        # 24-hour format (enum: "24h" or "12h")
        GSettingsTweakComboRow(
            _("Time Format"),
            "org.gnome.desktop.interface",
            "clock-format",
            key_options=(
                (_("24-Hour"), "24h"),
                (_("12-Hour"), "12h"),
            )
        ),
        # Show date in system clock
        GSettingsTweakSwitchRow(
            _("Show Date in Clock"),
            "org.gnome.desktop.interface",
            "clock-show-date",
        ),
        # Show weekday in system clock
        GSettingsTweakSwitchRow(
            _("Show Weekday in Clock"),
            "org.gnome.desktop.interface",
            "clock-show-weekday",
        ),
        # Show seconds in system clock
        GSettingsTweakSwitchRow(
            _("Show Seconds in Clock"),
            "org.gnome.desktop.interface",
            "clock-show-seconds",
        ),
    ),
    # Calendar Display Settings (affected by LC_TIME from region setting)
    TweakPreferencesGroup(
        _("Calendar"),
        "calendar-settings",
        # Show ISO week dates (controlled by LC_TIME format)
        GSettingsTweakSwitchRow(
            _("Show Week Dates"),
            "org.gnome.desktop.calendar",
            "show-weekdate",
        ),
    ),
)

