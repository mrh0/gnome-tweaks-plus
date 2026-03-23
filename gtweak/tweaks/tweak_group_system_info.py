# Copyright (c) 2026 MRH0
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

import logging
import builtins
import os
import socket
import platform
import re
from pathlib import Path
from gi.repository import Gtk, Adw, GLib
from gtweak.tweakmodel import Tweak, TweakGroup
from gtweak.widgets import TweakPreferencesPage, TweakPreferencesGroup

LOG = logging.getLogger(__name__)

# Ensure translation function is available globally
if not hasattr(builtins, '_'):
    builtins._ = lambda msg: msg

_ = builtins._


def _format_text(text):
    """Format text for better readability"""
    if not text:
        return _("Unknown")
    return str(text).strip()


def _escape_markup(text):
    """Escape special characters for use in GTK markup"""
    if not text:
        return text
    text = str(text)
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


class SystemInfoRow(Adw.ExpanderRow, Tweak):
    """Expandable system information row"""

    def __init__(self, title, info_getter, uid, description=None, details_getter=None, **options):
        Adw.ExpanderRow.__init__(self)
        Tweak.__init__(
            self,
            title=title,
            description=description or title,
            uid=uid,
            **options
        )
        
        try:
            info = info_getter()
            formatted_info = _format_text(info)
            
            self.set_title(title)
            self.set_subtitle(_escape_markup(formatted_info))
            self.set_selectable(False)
            
            # Add detailed information in expandable rows if provided
            if details_getter:
                try:
                    details = details_getter()
                    for detail_title, detail_value in details.items():
                        detail_row = Adw.ActionRow()
                        detail_row.set_title(detail_title)
                        detail_row.set_subtitle(_escape_markup(_format_text(detail_value)))
                        self.add_row(detail_row)
                except Exception as e:
                    LOG.debug(f"Failed to get details for {uid}: {e}")
            else:
                # Add a single detail row with the full information
                detail_row = Adw.ActionRow()
                detail_row.set_title(_("Value"))
                
                # Create a label for long text values
                value_label = Gtk.Label()
                value_label.set_label(_escape_markup(formatted_info))
                value_label.set_selectable(True)
                value_label.set_wrap(True)
                value_label.add_css_class("monospace")
                detail_row.set_child(value_label)
                self.add_row(detail_row)
                
        except Exception as e:
            LOG.warning(f"Failed to create system info row for {uid}: {e}")
            self.set_title(title)
            self.set_subtitle(_("Error getting info"))


class OSVersionRow(SystemInfoRow):
    """Display OS version information"""

    def __init__(self, **options):
        def get_os_info():
            try:
                os_release = Path("/etc/os-release")
                if os_release.exists():
                    info = {}
                    with open(os_release) as f:
                        for line in f:
                            if '=' in line:
                                key, value = line.strip().split('=', 1)
                                info[key] = value.strip('"')
                    
                    pretty_name = info.get('PRETTY_NAME', info.get('NAME', 'Unknown'))
                    version = info.get('VERSION_ID', info.get('VERSION', ''))
                    
                    if version:
                        return f"{pretty_name}"
                    return pretty_name
            except Exception as e:
                LOG.warning(f"Failed to read OS info: {e}")
            
            return platform.system()

        def get_os_details():
            try:
                details = {}
                
                # Add architecture info
                try:
                    details[_("Architecture")] = platform.machine()
                except:
                    pass
                
                os_release = Path("/etc/os-release")
                if os_release.exists():
                    info = {}
                    with open(os_release) as f:
                        for line in f:
                            if '=' in line:
                                key, value = line.strip().split('=', 1)
                                info[key] = value.strip('"')
                    
                    if info.get('PRETTY_NAME'):
                        details[_("Pretty Name")] = info['PRETTY_NAME']
                    if info.get('VERSION_ID'):
                        details[_("Version ID")] = info['VERSION_ID']
                    if info.get('VERSION'):
                        details[_("Version")] = info['VERSION']
                    if info.get('VERSION_CODENAME'):
                        details[_("Codename")] = info['VERSION_CODENAME']
                
                return details
            except:
                pass
            return {}

        super().__init__(
            title=_("OS Version"),
            info_getter=get_os_info,
            details_getter=get_os_details,
            uid="os_version",
            description=_("Operating system version and distribution"),
            **options
        )


class HostnameRow(Adw.ActionRow, Tweak):
    """Display system hostname (simple row, no expander)"""

    def __init__(self, **options):
        Adw.ActionRow.__init__(self)
        
        def get_hostname():
            try:
                return socket.gethostname()
            except Exception as e:
                LOG.warning(f"Failed to get hostname: {e}")
                return "Unknown"
        
        hostname = get_hostname()
        
        Tweak.__init__(
            self,
            title=_("Hostname"),
            description=_("Computer name on the network"),
            uid="hostname",
            **options
        )
        
        self.set_title(_("Hostname"))
        self.set_subtitle(_escape_markup(_format_text(hostname)))
        self.set_selectable(False)


class KernelRow(SystemInfoRow):
    """Display kernel information"""

    def __init__(self, **options):
        def get_kernel_info():
            try:
                kernel_release = platform.release()
                return kernel_release
            except Exception as e:
                LOG.warning(f"Failed to get kernel info: {e}")
                return "Unknown"

        def get_kernel_details():
            try:
                details = {}
                details[_("System")] = platform.system()
                details[_("Release")] = platform.release()
                
                # Try to get kernel version
                try:
                    with open("/proc/version") as f:
                        version_line = f.read().split('#')[0].strip()
                        # Extract just the version part
                        import re
                        match = re.search(r'version [\d.]+', version_line)
                        if match:
                            details[_("Kernel Version")] = match.group(0)
                except:
                    pass
                
                return details
            except:
                return {}

        super().__init__(
            title=_("Kernel"),
            info_getter=get_kernel_info,
            details_getter=get_kernel_details,
            uid="kernel",
            description=_("Linux kernel version"),
            **options
        )




class RAMRow(SystemInfoRow):
    """Display installed RAM"""

    def __init__(self, **options):
        def get_ram_info():
            try:
                with open("/proc/meminfo") as f:
                    mem_info = {}
                    for line in f:
                        if ':' in line:
                            key, value = line.split(':', 1)
                            mem_info[key.strip()] = int(value.split()[0])
                    
                    mem_total_kb = mem_info.get('MemTotal', 0)
                    mem_gb = mem_total_kb / 1024 / 1024
                    return f"{mem_gb:.2f} GB"
            except Exception as e:
                LOG.warning(f"Failed to get RAM info: {e}")
            
            return "Unknown"

        def get_ram_details():
            try:
                details = {}
                with open("/proc/meminfo") as f:
                    mem_info = {}
                    for line in f:
                        if ':' in line:
                            key, value = line.split(':', 1)
                            mem_info[key.strip()] = int(value.split()[0])
                
                total = mem_info.get('MemTotal', 0) / 1024 / 1024
                available = mem_info.get('MemAvailable', 0) / 1024 / 1024
                used = total - available
                
                details[_("Total")] = f"{total:.2f} GB"
                details[_("Available")] = f"{available:.2f} GB"
                details[_("Used")] = f"{used:.2f} GB"
                
                buffers = mem_info.get('Buffers', 0) / 1024 / 1024
                cached = mem_info.get('Cached', 0) / 1024 / 1024
                if buffers > 0:
                    details[_("Buffers")] = f"{buffers:.2f} GB"
                if cached > 0:
                    details[_("Cached")] = f"{cached:.2f} GB"
                
                return details
            except:
                return {}

        super().__init__(
            title=_("RAM"),
            info_getter=get_ram_info,
            details_getter=get_ram_details,
            uid="ram_installed",
            description=_("Total system memory"),
            **options
        )


class CPURow(SystemInfoRow):
    """Display CPU information"""

    def __init__(self, **options):
        def get_cpu_info():
            try:
                # First try to use platform.processor()
                processor = platform.processor()
                if processor and processor.strip():
                    # Extract just the CPU model name
                    return processor
                
                # Fallback: read from /proc/cpuinfo
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if line.startswith("model name"):
                            model = line.split(":", 1)[1].strip()
                            # Clean up the model name
                            model = re.sub(r'\(R\)|\(TM\)', '', model).strip()
                            return model
            except Exception as e:
                LOG.warning(f"Failed to get CPU info: {e}")
            
            return "Unknown"

        def get_cpu_details():
            try:
                details = {}
                details[_("Cores")] = f"{os.cpu_count()}"
                
                # Get CPU frequency
                try:
                    with open("/proc/cpuinfo") as f:
                        for line in f:
                            if line.startswith("cpu MHz"):
                                freq = float(line.split(":", 1)[1].strip())
                                details[_("Base Frequency")] = f"{freq:.0f} MHz"
                                break
                except:
                    pass
                
                # Get processor flags for feature detection
                try:
                    with open("/proc/cpuinfo") as f:
                        for line in f:
                            if line.startswith("flags"):
                                flags = line.split(":", 1)[1].strip().split()
                                if "avx2" in flags:
                                    features = ["AVX2"]
                                    if "avx" in flags:
                                        features.append("AVX")
                                    if "sse4_2" in flags:
                                        features.append("SSE4.2")
                                    if "vmx" in flags or "svm" in flags:
                                        features.append("Virtualization")
                                    if features:
                                        details[_("Features")] = ", ".join(features)
                                break
                except:
                    pass
                
                return details
            except:
                return {}

        super().__init__(
            title=_("CPU"),
            info_getter=get_cpu_info,
            details_getter=get_cpu_details,
            uid="cpu",
            description=_("Processor information"),
            **options
        )



class CPUCountRow(SystemInfoRow):
    """Display number of CPU cores"""

    def __init__(self, **options):
        def get_cpu_count():
            try:
                physical_cores = os.cpu_count()
                if physical_cores:
                    return f"{physical_cores} cores"
                return "Unknown"
            except Exception as e:
                LOG.warning(f"Failed to get CPU count: {e}")
                return "Unknown"

        def get_cpu_details():
            details = {}
            try:
                with open("/proc/cpuinfo") as f:
                    content = f.read()
                    logical_cores = len([line for line in content.split('\n') if line.startswith("processor")])
                    physical_cores = os.cpu_count()
                    
                    details[_("Logical Cores")] = f"{logical_cores}"
                    details[_("Physical Cores")] = f"{physical_cores}"
                    
                    # Calculate threads per core
                    if logical_cores and physical_cores:
                        threads_per_core = logical_cores // physical_cores
                        details[_("Threads per Core")] = f"{threads_per_core}"
            except:
                pass
            return details

        super().__init__(
            title=_("CPU Cores"),
            info_getter=get_cpu_count,
            details_getter=get_cpu_details,
            uid="cpu_cores",
            description=_("Number of processor cores"),
            **options
        )


class GPURow(SystemInfoRow):
    """Display GPU/Video card information"""

    def __init__(self, **options):
        def get_gpu_info():
            # Try lspci first (most reliable)
            try:
                result = os.popen("lspci 2>/dev/null | grep -i 'vga\\|3d' | head -1").read().strip()
                if result:
                    parts = result.split(': ', 1)
                    if len(parts) > 1:
                        return parts[1]
            except Exception as e:
                LOG.debug(f"lspci attempt failed: {e}")
            
            # Try glxinfo as fallback
            try:
                result = os.popen("glxinfo 2>/dev/null | grep -i 'renderer' | head -1").read().strip()
                if result:
                    parts = result.split(': ', 1)
                    if len(parts) > 1:
                        return parts[1].strip()
            except Exception as e:
                LOG.debug(f"glxinfo attempt failed: {e}")
            
            # Try reading from sysfs (Intel/AMD)
            try:
                for device_dir in Path("/sys/class/drm").glob("card*"):
                    try:
                        driver_link = device_dir / "device" / "driver"
                        if driver_link.exists():
                            driver_name = os.path.basename(os.readlink(driver_link))
                            return driver_name
                    except:
                        pass
            except Exception as e:
                LOG.debug(f"sysfs attempt failed: {e}")
            
            return "Unknown"

        def get_gpu_details():
            details = {}
            try:
                # Get all GPUs from lspci
                result = os.popen("lspci 2>/dev/null | grep -i 'vga\\|3d'").read().strip()
                if result:
                    gpus = []
                    for line in result.split('\n'):
                        if line:
                            parts = line.split(': ', 1)
                            if len(parts) > 1:
                                gpus.append(parts[1])
                    
                    if len(gpus) > 1:
                        for i, gpu in enumerate(gpus, 1):
                            details[_("GPU %d") % i] = gpu
                    elif gpus:
                        details[_("Device")] = gpus[0]
            except:
                pass
            
            # Try to get OpenGL renderer info
            try:
                result = os.popen("glxinfo 2>/dev/null | grep -i 'renderer'").read().strip()
                if result:
                    parts = result.split(': ', 1)
                    if len(parts) > 1:
                        details[_("Renderer")] = parts[1].strip()
            except:
                pass
            
            # Try to get OpenGL version
            try:
                result = os.popen("glxinfo 2>/dev/null | grep 'OpenGL version'").read().strip()
                if result:
                    parts = result.split(': ', 1)
                    if len(parts) > 1:
                        details[_("OpenGL Version")] = parts[1].strip()
            except:
                pass
            
            return details

        super().__init__(
            title=_("GPU"),
            info_getter=get_gpu_info,
            details_getter=get_gpu_details,
            uid="gpu",
            description=_("Graphics processor information"),
            **options
        )


class DesktopEnvironmentRow(SystemInfoRow):
    """Display desktop environment"""

    def __init__(self, **options):
        def get_desktop_env():
            try:
                de_env = os.environ.get('XDG_CURRENT_DESKTOP')
                if de_env:
                    return de_env
                
                de_env = os.environ.get('DESKTOP_SESSION')
                if de_env:
                    return de_env.upper()
                
                return "Unknown"
            except Exception as e:
                LOG.warning(f"Failed to get desktop environment: {e}")
                return "Unknown"

        def get_de_details():
            details = {}
            try:
                xdg_de = os.environ.get('XDG_CURRENT_DESKTOP', 'Unknown')
                session = os.environ.get('DESKTOP_SESSION', 'Unknown')
                session_type = os.environ.get('XDG_SESSION_TYPE', 'Unknown')
                
                details[_("XDG_CURRENT_DESKTOP")] = xdg_de
                details[_("DESKTOP_SESSION")] = session
                details[_("Windowing System")] = session_type.capitalize() if session_type != 'Unknown' else session_type
                
                # Try to get GTK version
                try:
                    import gi
                    gi.require_version('Gtk', '4.0')
                    from gi.repository import Gtk
                    details[_("GTK Version")] = f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}"
                except:
                    pass
            except:
                pass
            
            return details

        super().__init__(
            title=_("Desktop Environment"),
            info_getter=get_desktop_env,
            details_getter=get_de_details,
            uid="desktop_env",
            description=_("Current desktop environment"),
            **options
        )


class UptimeRow(Adw.ActionRow, Tweak):
    """Display system uptime (simple row, no expander)"""

    def __init__(self, **options):
        Adw.ActionRow.__init__(self)
        
        def get_uptime():
            try:
                with open("/proc/uptime") as f:
                    uptime_seconds = float(f.read().split()[0])
                    
                    days = int(uptime_seconds // 86400)
                    hours = int((uptime_seconds % 86400) // 3600)
                    minutes = int((uptime_seconds % 3600) // 60)
                    
                    parts = []
                    if days > 0:
                        parts.append(f"{days}d")
                    if hours > 0:
                        parts.append(f"{hours}h")
                    if minutes > 0:
                        parts.append(f"{minutes}m")
                    
                    return " ".join(parts) if parts else _("Just started")
            except Exception as e:
                LOG.warning(f"Failed to get uptime: {e}")
                return "Unknown"
        
        uptime = get_uptime()
        
        Tweak.__init__(
            self,
            title=_("Uptime"),
            description=_("Time since last system reboot"),
            uid="uptime",
            **options
        )
        
        self.set_title(_("Uptime"))
        self.set_subtitle(_escape_markup(_format_text(uptime)))
        self.set_selectable(False)




# Create system info tweak group
try:
    system_info_tweaks = [
        HostnameRow(),
        UptimeRow(),
        OSVersionRow(),
        DesktopEnvironmentRow(),
        KernelRow(),
    ]
    
    hardware_tweaks = [
        CPURow(),
        CPUCountRow(),
        RAMRow(),
        GPURow(),
    ]
    
    TWEAK_GROUP = TweakPreferencesPage(
        "system_info",
        _("System Info"),
        TweakPreferencesGroup(
            _("System"),
            "system",
            *system_info_tweaks
        ),
        TweakPreferencesGroup(
            _("Hardware"),
            "hardware",
            *hardware_tweaks
        ),
        uid="system_info_group"
    )
except Exception as e:
    LOG.error(f"Failed to initialize system info tweaks: {e}")
    TWEAK_GROUP = TweakPreferencesPage("system_info", _("System Info"))
