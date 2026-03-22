# Copyright (c) 2011 John Stowers
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

"""
Audio management module for gnome-tweaks.
Provides support for PipeWire audio server.
Uses flatpak-spawn --host when running in Flatpak sandbox.
"""

from gtweak.audio.audio_manager import (
    PipeWireManager,
    HAS_PIPEWIRE,
    get_audio_manager
)

__all__ = [
    'PipeWireManager',
    'HAS_PIPEWIRE',
    'get_audio_manager'
]
