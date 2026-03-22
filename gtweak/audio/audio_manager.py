# Copyright (c) 2011 John Stowers
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

"""
Audio manager for gnome-tweaks.
Supports PipeWire audio server via wpctl.
Uses flatpak-spawn --host when running in Flatpak sandbox.
Uses pw-dump for machine-readable device enumeration.
"""

import logging
import subprocess
import json
import os
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

# Detect if running in Flatpak sandbox
IN_FLATPAK = os.path.exists('/.flatpak-info')

if IN_FLATPAK:
    logger.info("Audio manager: Running in Flatpak sandbox, will use flatpak-spawn --host for wpctl")
else:
    logger.info("Audio manager: Running natively, will use wpctl directly")


def _has_pipewire() -> bool:
    """Check if PipeWire is available via wpctl/pw-dump"""
    
    # Check if pw-dump is available (preferred for device enumeration)
    try:
        if IN_FLATPAK:
            wpctl_cmd = ['flatpak-spawn', '--host', 'pw-dump']
        else:
            wpctl_cmd = ['pw-dump']
        
        result = subprocess.run(wpctl_cmd, capture_output=True, check=False, timeout=3, text=True)
        if result.returncode == 0:
            logger.debug("PipeWire detected: pw-dump command works")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    
    # Also try wpctl as fallback
    try:
        if IN_FLATPAK:
            wpctl_cmd = ['flatpak-spawn', '--host', 'wpctl', 'status']
            logger.debug(f"PipeWire detection (Flatpak): trying {' '.join(wpctl_cmd)}")
        else:
            wpctl_cmd = ['wpctl', 'status']
            logger.debug(f"PipeWire detection (native): trying {' '.join(wpctl_cmd)}")
        
        result = subprocess.run(wpctl_cmd, capture_output=True, check=False, timeout=3, text=True)
        if result.returncode == 0:
            logger.debug("PipeWire detected: wpctl command works")
            return True
        else:
            logger.debug(f"wpctl returned exit code {result.returncode}")
            return False
    except FileNotFoundError as e:
        logger.debug(f"flatpak-spawn or wpctl not found: {e}")
        return False
    except subprocess.TimeoutExpired:
        logger.debug("wpctl status timed out (>3s)")
        return False
    except Exception as e:
        logger.debug(f"wpctl detection error: {e}")
    
    # Fall back to checking for PipeWire socket
    try:
        uid = os.getuid()
        pipewire_socket = f"/run/user/{uid}/pipewire-0"
        if os.path.exists(pipewire_socket):
            logger.debug(f"PipeWire detected: socket exists at {pipewire_socket}")
            return True
    except Exception as e:
        logger.debug(f"Could not check PipeWire socket: {e}")
    
    logger.debug("PipeWire not detected by any method")
    return False


HAS_PIPEWIRE = _has_pipewire()

if not HAS_PIPEWIRE:
    if IN_FLATPAK:
        logger.warning("Running in Flatpak: wpctl not available. Make sure the Flatpak has proper audio permissions (--socket=pulseaudio)")
    else:
        logger.warning("wpctl not available - audio device/volume control features will be disabled")
else:
    logger.info("Using PipeWire (wpctl) for audio control")


class PipeWireManager:
    """Manager for PipeWire device and volume operations using wpctl"""
    
    def __init__(self):
        """Initialize PipeWire manager"""
        self.connected = HAS_PIPEWIRE
        logger.debug(f"PipeWireManager.__init__: connected={self.connected}")
    
    def is_available(self) -> bool:
        """Check if PipeWire (wpctl) is available"""
        return self.connected
    
    def _run_wpctl(self, *args) -> Optional[str]:
        """Run wpctl command and return output, using flatpak-spawn if in Flatpak"""
        try:
            if IN_FLATPAK:
                cmd = ['flatpak-spawn', '--host', 'wpctl'] + list(args)
            else:
                cmd = ['wpctl'] + list(args)
            
            result = subprocess.run(cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.warning(f"wpctl {' '.join(args)}: exit code {result.returncode}")
                return None
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.debug(f"wpctl error: {type(e).__name__}")
            return None
        except Exception as e:
            logger.error(f"wpctl error: {e}")
            return None
    
    def _run_pw_dump(self) -> Optional[List]:
        """Run pw-dump and parse JSON output"""
        try:
            if IN_FLATPAK:
                cmd = ['flatpak-spawn', '--host', 'pw-dump']
            else:
                cmd = ['pw-dump']
            
            result = subprocess.run(cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            
            if result.returncode != 0:
                logger.warning(f"pw-dump failed with exit code {result.returncode}, stderr: {result.stderr}")
                return None
            
            output = result.stdout.strip()
            if not output:
                logger.warning(f"pw-dump returned empty output, stderr: {result.stderr}")
                return None
            
            try:
                devices = json.loads(output)
                if not isinstance(devices, list):
                    logger.error(f"pw-dump returned non-list type: {type(devices)}")
                    return None
                
                logger.info(f"pw-dump: parsed {len(devices)} items")
                return devices
            except json.JSONDecodeError as e:
                logger.error(f"pw-dump JSON parse failed: {e}")
                logger.debug(f"pw-dump output (first 500 chars): {output[:500]}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("pw-dump: command timeout (5s)")
            return None
        except FileNotFoundError:
            logger.error("pw-dump: command not found")
            return None
        except Exception as e:
            logger.error(f"pw-dump: {type(e).__name__}: {e}")
            return None
    
    # ========== SINK (OUTPUT) OPERATIONS ==========
    
    def get_sinks(self) -> List[Tuple[str, str, str]]:
        """
        Get list of audio output devices (sinks) from PipeWire via pw-dump.
        
        Returns:
            List of tuples (sink_id, sink_description, sink_id)
        """
        if not self.is_available():
            return []
        
        try:
            devices = self._run_pw_dump()
            if not devices:
                logger.warning("get_sinks: pw-dump returned no data")
                return []
            
            sinks = []
            for item in devices:
                try:
                    # Look at info.props.media.class for Audio/Sink
                    info = item.get('info', {})
                    if not info:
                        continue
                    
                    props = info.get('props', {})
                    media_class = props.get('media.class', '')
                    
                    if media_class == 'Audio/Sink':
                        device_id = str(item.get('id', ''))
                        if not device_id:
                            continue
                        
                        # Try multiple sources for a good device name
                        description = (
                            props.get('node.description', '').strip() or
                            props.get('node.nick', '').strip() or
                            props.get('alsa.card_name', '').strip() or
                            props.get('device.name', '').strip() or
                            props.get('dapi.alsa.card.name', '').strip() or
                            f'Sink {device_id}'
                        )
                        icon = props.get('device.icon-name', '').strip() or 'audio-speakers'
                        
                        logger.debug(f"Found sink: id={device_id}, desc={description}, icon={icon}")
                        sinks.append((device_id, description, icon))
                except (KeyError, TypeError, ValueError) as e:
                    logger.debug(f"Skipping malformed item: {e}")
                    continue
            
            if not sinks:
                logger.warning(f"get_sinks: no Audio/Sink items found in {len(devices)} pw-dump items")
            else:
                logger.info(f"get_sinks: found {len(sinks)} sinks")
            
            return sinks
        except Exception as e:
            logger.error(f"get_sinks: {type(e).__name__}: {e}", exc_info=True)
            return []
    
    def get_default_sink(self) -> Optional[str]:
        """Get the ID of the default output device"""
        if not self.is_available():
            return None
        
        try:
            devices = self._run_pw_dump()
            if not devices:
                logger.warning("get_default_sink: pw-dump returned no data")
                return None
            
            # Return the first Audio/Sink found
            for item in devices:
                try:
                    info = item.get('info', {})
                    props = info.get('props', {})
                    
                    if props.get('media.class') == 'Audio/Sink':
                        device_id = str(item.get('id', ''))
                        if device_id:
                            logger.debug(f"get_default_sink: {device_id}")
                            return device_id
                except (KeyError, TypeError, ValueError):
                    continue
            
            logger.warning("get_default_sink: no Audio/Sink found in pw-dump")
            return None
        except Exception as e:
            logger.error(f"get_default_sink: {type(e).__name__}: {e}")
            return None
    
    def set_default_sink(self, sink_name: str) -> bool:
        """Set the default audio output device"""
        if not self.is_available():
            return False
        
        try:
            logger.debug(f"set_default_sink: setting to '{sink_name}'")
            result = self._run_wpctl('set-default', sink_name)
            if result is not None:
                logger.info(f"Set default sink to: {sink_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error setting default sink: {e}")
            return False
    
    def get_sink_volume(self, sink_name: str) -> Optional[float]:
        """
        Get the volume level of a sink (0.0 to 1.5).
        
        Args:
            sink_name: Name or ID of the sink
            
        Returns:
            Volume as float (0.0-1.5) or None if error
        """
        if not self.is_available():
            return None
        
        try:
            logger.debug(f"get_sink_volume: getting for '{sink_name}'")
            output = self._run_wpctl('get-volume', sink_name)
            if output:
                logger.debug(f"  wpctl get-volume output: {output}")
                # Parse output like "Volume: 0.50" or "0.50"
                if ':' in output:
                    vol_str = output.split(':')[1].strip().split()[0]
                else:
                    vol_str = output.split()[0]
                return float(vol_str)
            return None
        except Exception as e:
            logger.error(f"Error getting sink volume: {e}")
            return None
    
    def set_sink_volume(self, sink_name: str, volume: float) -> bool:
        """
        Set the volume level of a sink.
        
        Args:
            sink_name: Name or ID of the sink
            volume: Volume value (0.0-1.5)
            
        Returns:
            True if successful
        """
        if not self.is_available():
            return False
        
        try:
            logger.debug(f"set_sink_volume: setting '{sink_name}' to {volume}")
            result = self._run_wpctl('set-volume', sink_name, str(volume))
            if result is not None:
                logger.info(f"Set sink {sink_name} volume to: {volume}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error setting sink volume: {e}")
            return False
    
    # ========== SOURCE (INPUT) OPERATIONS ==========
    
    def get_sources(self) -> List[Tuple[str, str, str]]:
        """
        Get list of audio input devices (sources) from PipeWire via pw-dump.
        
        Returns:
            List of tuples (source_id, source_description, source_id)
        """
        if not self.is_available():
            return []
        
        try:
            devices = self._run_pw_dump()
            if not devices:
                logger.warning("get_sources: pw-dump returned no data")
                return []
            
            sources = []
            for item in devices:
                try:
                    # Look at info.props.media.class for Audio/Source
                    info = item.get('info', {})
                    if not info:
                        continue
                    
                    props = info.get('props', {})
                    media_class = props.get('media.class', '')
                    
                    if media_class == 'Audio/Source':
                        device_id = str(item.get('id', ''))
                        if not device_id:
                            continue
                        
                        # Try multiple sources for a good device name
                        description = (
                            props.get('device.description', '').strip() or
                            props.get('device.nick', '').strip() or
                            props.get('alsa.card_name', '').strip() or
                            props.get('device.name', '').strip() or
                            f'Source {device_id}'
                        )
                        
                        icon = props.get('device.icon-name', '').strip() or 'audio-input-microphone'

                        logger.debug(f"Found source: id={device_id}, desc={description}, icon={icon}")
                        sources.append((device_id, description, icon))
                except (KeyError, TypeError, ValueError) as e:
                    logger.debug(f"Skipping malformed item: {e}")
                    continue
            
            if not sources:
                logger.warning(f"get_sources: no Audio/Source items found in {len(devices)} pw-dump items")
            else:
                logger.info(f"get_sources: found {len(sources)} sources")
            
            return sources
        except Exception as e:
            logger.error(f"get_sources: {type(e).__name__}: {e}", exc_info=True)
            return []
    
    def get_default_source(self) -> Optional[str]:
        """Get the ID of the default input device"""
        if not self.is_available():
            return None
        
        try:
            devices = self._run_pw_dump()
            if not devices:
                logger.warning("get_default_source: pw-dump returned no data")
                return None
            
            # Return the first Audio/Source found
            for item in devices:
                try:
                    info = item.get('info', {})
                    props = info.get('props', {})
                    
                    if props.get('media.class') == 'Audio/Source':
                        device_id = str(item.get('id', ''))
                        if device_id:
                            logger.debug(f"get_default_source: {device_id}")
                            return device_id
                except (KeyError, TypeError, ValueError):
                    continue
            
            logger.warning("get_default_source: no Audio/Source found in pw-dump")
            return None
        except Exception as e:
            logger.error(f"get_default_source: {type(e).__name__}: {e}")
            return None
    
    def set_default_source(self, source_name: str) -> bool:
        """Set the default audio input device"""
        if not self.is_available():
            return False
        
        try:
            logger.debug(f"set_default_source: setting to '{source_name}'")
            result = self._run_wpctl('set-default', source_name)
            if result is not None:
                logger.info(f"Set default source to: {source_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error setting default source: {e}")
            return False
    
    def get_source_volume(self, source_name: str) -> Optional[float]:
        """
        Get the volume level of a source (0.0 to 1.5).
        
        Args:
            source_name: Name or ID of the source
            
        Returns:
            Volume as float (0.0-1.5) or None if error
        """
        if not self.is_available():
            return None
        
        try:
            logger.debug(f"get_source_volume: getting for '{source_name}'")
            output = self._run_wpctl('get-volume', source_name)
            if output:
                logger.debug(f"  wpctl get-volume output: {output}")
                # Parse output like "Volume: 0.50" or "0.50"
                if ':' in output:
                    vol_str = output.split(':')[1].strip().split()[0]
                else:
                    vol_str = output.split()[0]
                return float(vol_str)
            return None
        except Exception as e:
            logger.error(f"Error getting source volume: {e}")
            return None
    
    def set_source_volume(self, source_name: str, volume: float) -> bool:
        """
        Set the volume level of a source.
        
        Args:
            source_name: Name or ID of the source
            volume: Volume value (0.0-1.5)
            
        Returns:
            True if successful
        """
        if not self.is_available():
            return False
        
        try:
            logger.debug(f"set_source_volume: setting '{source_name}' to {volume}")
            result = self._run_wpctl('set-volume', source_name, str(volume))
            if result is not None:
                logger.info(f"Set source {source_name} volume to: {volume}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error setting source volume: {e}")
            return False
    
    def close(self):
        """Close the manager and clean up resources"""
        logger.debug("PipeWireManager.close()")


def get_audio_manager() -> Optional[PipeWireManager]:
    """
    Factory function to get the audio manager.
    Returns PipeWireManager if available, None otherwise.
    """
    if HAS_PIPEWIRE:
        logger.debug("get_audio_manager: creating PipeWireManager")
        pw_mgr = PipeWireManager()
        if pw_mgr.is_available():
            logger.info("get_audio_manager: using PipeWireManager")
            return pw_mgr
    
    logger.warning("get_audio_manager: no audio manager available")
    return None
