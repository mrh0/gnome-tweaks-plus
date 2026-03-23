# Copyright (c) 2026 MRH0
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

"""
Display management module for gnome-tweaks.
Provides display configuration and control.
"""

from .display_manager import (
    get_display_manager,
    DBusDisplayManager,
    DisplayMode,
    DisplayConnectorType,
)

__all__ = [
    'get_display_manager',
    'DBusDisplayManager',
    'DisplayMode',
    'DisplayConnectorType',
]
