# Copyright (c) 2026 MRH0
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSES/GPL-3.0

"""
Interactive screen arrangement widget for display configuration.
Allows users to visually arrange displays and drag them to new positions.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from enum import IntEnum

try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Gdk', '4.0')
    from gi.repository import Gtk, Gdk, GLib, GObject
except (ImportError, ValueError):
    Gtk = None
    Gdk = None
    GLib = None
    GObject = None

logger = logging.getLogger(__name__)


class ScreenArrangementCanvas(Gtk.DrawingArea):
    """
    Canvas for displaying and arranging multiple displays.
    Allows drag-and-drop repositioning of displays with proportional rendering.
    """
    
    # Padding and sizing constants
    CANVAS_PADDING = 40
    MIN_DISPLAY_SIZE = 80
    MAX_DISPLAY_SIZE = 300
    GRID_SIZE = 10  # For snap-to-grid functionality
    
    def __init__(self):
        """Initialize the screen arrangement canvas"""
        super().__init__()
        
        self.set_size_request(600, 400)
        
        # Display data
        self.displays: List[Dict[str, Any]] = []
        self.arrangement: List[Dict[str, Any]] = []  # Current arrangement state
        
        # Interaction state
        self.dragging_display_idx: Optional[int] = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.drag_start_arr_x = 0  # Initial arrangement x when drag started
        self.drag_start_arr_y = 0  # Initial arrangement y when drag started
        self.display_render_info: List[Dict[str, Any]] = []  # Cached rendering info
        
        # Set up GTK4 draw callback (not a signal in GTK4)
        self.set_draw_func(self._on_draw)
        
        # Set up mouse event handling
        motion_controller = Gtk.EventControllerMotion()
        motion_controller.connect("motion", self._on_mouse_motion)
        self.add_controller(motion_controller)
        
        # Set up click handling
        gesture = Gtk.GestureClick.new()
        gesture.connect("pressed", self._on_button_pressed)
        gesture.connect("released", self._on_button_released)
        self.add_controller(gesture)
        
        # Cursor tracking
        self.set_cursor(Gdk.Cursor.new_from_name("default"))
    
    def set_displays(self, displays: List[Dict[str, Any]]):
        """
        Set the displays to arrange.
        
        Args:
            displays: List of display dicts from display_manager
        """
        self.displays = displays
        self.arrangement = []
        
        # Initialize arrangement from current display positions
        for display in displays:
            self.arrangement.append({
                'connector': display.get('connector'),
                'x': display.get('x', 0),
                'y': display.get('y', 0),
                'mode_idx': display.get('mode_idx', 0),
                'scale': display.get('scale', 1.0),
                'transform': display.get('transform', 0),
                'primary': display.get('primary', False),
                'physical_width': display.get('physical_width', 1920),
                'physical_height': display.get('physical_height', 1080),
                'name': display.get('name', 'Unknown')
            })
        
        logger.debug(f"ScreenArrangementCanvas: Loaded {len(self.displays)} displays")
        self.queue_draw()
    
    def get_arrangement(self) -> List[Dict[str, Any]]:
        """Get the current display arrangement configuration"""
        return self.arrangement
    
    def _on_draw(self, widget, cr, width, height, user_data=None):
        """Draw the screen arrangement canvas (GTK4 set_draw_func callback)"""
        try:
            # Draw background
            cr.set_source_rgb(0.95, 0.95, 0.95)
            cr.rectangle(0, 0, width, height)
            cr.fill()
            
            # Update rendering info
            self.display_render_info = self._calculate_display_positions(width, height)
            
            # Draw each display
            for idx, info in enumerate(self.display_render_info):
                self._draw_display(cr, idx, info)
        
        except Exception as e:
            logger.error(f"Error drawing canvas: {e}")
        
        return False
    
    def _draw_display(self, cr, idx: int, info: Dict[str, Any]):
        """Draw a single display"""
        x = info['x']
        y = info['y']
        size_w = info['size_w']
        size_h = info['size_h']
        display = info['display']
        
        # Determine colors
        if idx == self.dragging_display_idx:
            # Dragging - highlight
            cr.set_source_rgb(0.2, 0.4, 0.8)
        elif display.get('primary'):
            # Primary display - different color
            cr.set_source_rgb(0.2, 0.7, 0.2)
        else:
            # Normal display
            cr.set_source_rgb(0.3, 0.3, 0.3)
        
        # Draw rounded rectangle
        radius = 4
        cr.new_sub_path()
        cr.arc(x + radius, y + radius, radius, 3.14159, 3.14159 * 1.5)
        cr.arc(x + size_w - radius, y + radius, radius, 3.14159 * 1.5, 0)
        cr.arc(x + size_w - radius, y + size_h - radius, radius, 0, 3.14159 * 0.5)
        cr.arc(x + radius, y + size_h - radius, radius, 3.14159 * 0.5, 3.14159)
        cr.close_path()
        cr.fill()
        
        # Draw border
        cr.set_source_rgb(0.1, 0.1, 0.1)
        cr.set_line_width(2)
        cr.new_sub_path()
        cr.arc(x + radius, y + radius, radius, 3.14159, 3.14159 * 1.5)
        cr.arc(x + size_w - radius, y + radius, radius, 3.14159 * 1.5, 0)
        cr.arc(x + size_w - radius, y + size_h - radius, radius, 0, 3.14159 * 0.5)
        cr.arc(x + radius, y + size_h - radius, radius, 3.14159 * 0.5, 3.14159)
        cr.close_path()
        cr.stroke()
        
        # Draw text (display name and resolution)
        text_color = (0.9, 0.9, 0.9) if display.get('primary') else (1, 1, 1)
        cr.set_source_rgb(*text_color)
        
        # Display name
        name = display.get('name', 'Unknown')
        resolution = display.get('resolution', 'Unknown')
        
        # GTK4: Create Pango layout directly
        import gi
        gi.require_version('Pango', '1.0')
        gi.require_version('PangoCairo', '1.0')
        from gi.repository import Pango, PangoCairo
        
        pango_layout = Pango.Layout.new(self.get_pango_context())
        pango_layout.set_text(f"{name}\n{resolution}", -1)
        font_desc = Pango.FontDescription.new()
        font_desc.set_size(10 * 1024)  # Pango units
        pango_layout.set_font_description(font_desc)
        
        cr.move_to(x + 8, y + 8)
        PangoCairo.show_layout(cr, pango_layout)
        
        # Primary display indicator
        if display.get('primary'):
            cr.set_source_rgb(1, 1, 0)
            cr.set_font_size(10)
            cr.move_to(x + size_w - 20, y + 5)
            cr.show_text("★")
    
    def _calculate_display_positions(self, canvas_width: int, canvas_height: int) -> List[Dict[str, Any]]:
        """
        Calculate positions and sizes for all displays on the canvas.
        Maintains aspect ratios and arranges them visually.
        
        Returns:
            List of render info dicts with x, y, size_w, size_h, display
        """
        if not self.arrangement:
            return []
        
        render_info = []
        
        # Calculate bounding box of all displays
        min_x = min(arr['x'] for arr in self.arrangement) if self.arrangement else 0
        max_x = max(arr['x'] + arr['physical_width'] for arr in self.arrangement) if self.arrangement else 0
        min_y = min(arr['y'] for arr in self.arrangement) if self.arrangement else 0
        max_y = max(arr['y'] + arr['physical_height'] for arr in self.arrangement) if self.arrangement else 0
        
        total_width = max_x - min_x if max_x > min_x else 1920
        total_height = max_y - min_y if max_y > min_y else 1080
        
        # Calculate scale to fit within canvas
        available_width = canvas_width - (self.CANVAS_PADDING * 2)
        available_height = canvas_height - (self.CANVAS_PADDING * 2)
        
        scale_x = available_width / total_width if total_width > 0 else 1
        scale_y = available_height / total_height if total_height > 0 else 1
        scale = min(scale_x, scale_y, 1.0)  # Don't scale up
        
        # Draw each display
        for arr_idx, arrangement in enumerate(self.arrangement):
            display = next((d for d in self.displays if d['connector'] == arrangement['connector']), None)
            if not display:
                continue
            
            # Calculate position relative to bounding box
            rel_x = arrangement['x'] - min_x
            rel_y = arrangement['y'] - min_y
            
            # Scale and offset to canvas
            canvas_x = self.CANVAS_PADDING + (rel_x * scale)
            canvas_y = self.CANVAS_PADDING + (rel_y * scale)
            
            # Calculate display size maintaining aspect ratio
            width_px = arrangement['physical_width'] * scale
            height_px = arrangement['physical_height'] * scale
            
            # Ensure minimum size
            width_px = max(width_px, self.MIN_DISPLAY_SIZE)
            height_px = max(height_px, self.MIN_DISPLAY_SIZE)
            
            info = {
                'x': canvas_x,
                'y': canvas_y,
                'size_w': width_px,
                'size_h': height_px,
                'display': display,
                'arrangement_idx': arr_idx,
                'original_x': arrangement['x'],
                'original_y': arrangement['y'],
                'scale_factor': scale
            }
            
            render_info.append(info)
        
        return render_info
    
    def _on_button_pressed(self, gesture, button, x, y):
        """Handle mouse button press"""
        # Find which display was clicked
        for idx, info in enumerate(self.display_render_info):
            if (info['x'] <= x <= info['x'] + info['size_w'] and
                info['y'] <= y <= info['y'] + info['size_h']):
                self.dragging_display_idx = idx
                self.drag_start_x = x
                self.drag_start_y = y
                # Save the initial arrangement position
                arr_idx = info['arrangement_idx']
                self.drag_start_arr_x = self.arrangement[arr_idx]['x']
                self.drag_start_arr_y = self.arrangement[arr_idx]['y']
                logger.debug(f"Start dragging display {idx} from ({x}, {y})")
                self.queue_draw()
                break
    
    def _on_button_released(self, gesture, button, x, y):
        """Handle mouse button release"""
        if self.dragging_display_idx is not None:
            logger.debug(f"Stopped dragging display {self.dragging_display_idx}")
            self.dragging_display_idx = None
            self.queue_draw()
    
    def _on_mouse_motion(self, controller, x, y):
        """Handle mouse motion for dragging"""
        if self.dragging_display_idx is not None and len(self.display_render_info) > self.dragging_display_idx:
            info = self.display_render_info[self.dragging_display_idx]
            
            # Calculate delta FROM THE INITIAL DRAG START
            delta_x = x - self.drag_start_x
            delta_y = y - self.drag_start_y
            
            # Convert canvas delta to world coordinates
            scale_factor = info['scale_factor']
            world_delta_x = int(delta_x / scale_factor)
            world_delta_y = int(delta_y / scale_factor)
            
            # Snap to grid
            world_delta_x = (world_delta_x // self.GRID_SIZE) * self.GRID_SIZE
            world_delta_y = (world_delta_y // self.GRID_SIZE) * self.GRID_SIZE
            
            # Update arrangement using INITIAL position + delta
            arr_idx = info['arrangement_idx']
            self.arrangement[arr_idx]['x'] = self.drag_start_arr_x + world_delta_x
            self.arrangement[arr_idx]['y'] = self.drag_start_arr_y + world_delta_y
            
            # Update cursor
            self.set_cursor(Gdk.Cursor.new_from_name("grab"))
            
            self.queue_draw()


class ScreenArrangementWidget(Gtk.Box):
    """
    Complete widget for screen arrangement with canvas and controls.
    """
    
    # Define custom signal for arrangement apply
    __gsignals__ = {
        'apply-arrangement': (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_PYOBJECT,))
    }
    
    def __init__(self):
        """Initialize the screen arrangement widget"""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)
        
        # Title
        title = Gtk.Label(label="Arrange Your Displays")
        title.add_css_class("title-3")
        self.append(title)
        
        # Description
        description = Gtk.Label(label="Drag the displays to arrange them. Green indicates the primary display.")
        description.set_wrap(True)
        description.add_css_class("dim-label")
        self.append(description)
        
        # Canvas in a scrolled window for responsiveness
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_min_content_width(600)
        scroll.set_min_content_height(300)
        
        self.canvas = ScreenArrangementCanvas()
        self.canvas.set_size_request(800, 400)  # Minimum drawing area size
        scroll.set_child(self.canvas)
        self.append(scroll)
        
        # Button box
        button_box = Gtk.Box(spacing=6)
        button_box.set_halign(Gtk.Align.END)
        
        # Reset button
        reset_btn = Gtk.Button(label="Reset")
        reset_btn.connect("clicked", self._on_reset_clicked)
        button_box.append(reset_btn)
        
        # Apply button
        apply_btn = Gtk.Button(label="Apply Configuration")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply_clicked)
        self.apply_button = apply_btn
        button_box.append(apply_btn)
        
        self.append(button_box)
    
    def set_displays(self, displays: List[Dict[str, Any]]):
        """Set the displays to arrange"""
        self.canvas.set_displays(displays)
    
    def get_arrangement(self) -> List[Dict[str, Any]]:
        """Get the current arrangement"""
        return self.canvas.get_arrangement()
    
    def _on_reset_clicked(self, button):
        """Reset arrangement to original positions"""
        # Reload from displays
        self.canvas.set_displays(self.canvas.displays)
        logger.debug("Reset display arrangement")
    
    def _on_apply_clicked(self, button):
        """Emit signal to apply arrangement"""
        self.emit("apply-arrangement", self.get_arrangement())
    
    def do_apply_arrangement(self, arrangement):
        """Default implementation - override in subclass if needed"""
        pass
