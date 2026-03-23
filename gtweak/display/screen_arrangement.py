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
    SNAP_DISTANCE = 80  # Distance in world coordinates to snap to edges (increased for aggressive snapping)
    
    def __init__(self):
        """Initialize the screen arrangement canvas"""
        super().__init__()
        
        self.set_size_request(600, 400)
        
        # Display data
        self.displays: List[Dict[str, Any]] = []
        self.arrangement: List[Dict[str, Any]] = []  # Current arrangement state
        
        # Callback for when arrangement changes
        self.on_arrangement_changed = None
        
        # Interaction state
        self.dragging_display_idx: Optional[int] = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.last_drag_x = 0
        self.last_drag_y = 0
        self.drag_start_arr_x = 0  # Initial arrangement x when drag started
        self.drag_start_arr_y = 0  # Initial arrangement y when drag started
        self.drag_arrangement_idx: Optional[int] = None  # Track the arrangement index being dragged
        self.drag_render_info: Optional[Dict[str, Any]] = None  # Render info snapshot at drag start
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
        
        # Auto-align nearly-aligned displays
        self._auto_align_displays()
        
        logger.debug(f"ScreenArrangementCanvas: Loaded {len(self.displays)} displays")
        self.queue_draw()
    
    def _auto_align_displays(self):
        """Auto-align displays that are nearly horizontal or vertical"""
        if len(self.arrangement) < 2:
            return
        
        ALIGNMENT_THRESHOLD = 50  # pixels
        
        # Check all pairs of displays
        for i in range(len(self.arrangement)):
            for j in range(i + 1, len(self.arrangement)):
                disp_i = self.arrangement[i]
                disp_j = self.arrangement[j]
                
                y_diff = abs(disp_i['y'] - disp_j['y'])
                x_diff = abs(disp_i['x'] - disp_j['x'])
                
                # If displays are nearly horizontal (similar Y, different X)
                if y_diff < ALIGNMENT_THRESHOLD and x_diff > ALIGNMENT_THRESHOLD:
                    # Align to the one with Y closest to 0
                    target_y = min(disp_i['y'], disp_j['y'])
                    disp_i['y'] = target_y
                    disp_j['y'] = target_y
                    logger.debug(f"Auto-aligned {disp_i['name']} and {disp_j['name']} horizontally to Y={target_y}")
                
                # If displays are nearly vertical (similar X, different Y)
                elif x_diff < ALIGNMENT_THRESHOLD and y_diff > ALIGNMENT_THRESHOLD:
                    # Align to the one with X closest to 0
                    target_x = min(disp_i['x'], disp_j['x'])
                    disp_i['x'] = target_x
                    disp_j['x'] = target_x
                    logger.debug(f"Auto-aligned {disp_i['name']} and {disp_j['name']} vertically to X={target_x}")
    
    def get_arrangement(self) -> List[Dict[str, Any]]:
        """Get the current display arrangement configuration"""
        return self.arrangement
    
    def _get_accent_color(self) -> Optional[Tuple[float, float, float]]:
        """
        Get the system accent color from the style context.
        Returns (r, g, b) tuple or None if not available.
        """
        try:
            style_context = self.get_style_context()
            # Try accent_bg_color first (common in Adwaita)
            found, color = style_context.lookup_color("accent_bg_color")
            if found:
                return (color.red, color.green, color.blue)
            
            # Fallback to accent_color
            found, color = style_context.lookup_color("accent_color")
            if found:
                return (color.red, color.green, color.blue)
            
            return None
        except Exception as e:
            logger.debug(f"Could not retrieve accent color: {e}")
            return None
    
    def _on_draw(self, widget, cr, width, height, user_data=None):
        """Draw the screen arrangement canvas (GTK4 set_draw_func callback)"""
        try:
            # Draw background
            cr.set_source_rgb(0.95, 0.95, 0.95)
            cr.rectangle(0, 0, width, height)
            cr.fill()
            
            # Update rendering info
            self.display_render_info = self._calculate_display_positions(width, height)
            
            # Draw each display, but save the dragging one for last (on top)
            dragging_info = None
            for idx, info in enumerate(self.display_render_info):
                if idx == self.dragging_display_idx:
                    dragging_info = (idx, info)
                else:
                    self._draw_display(cr, idx, info)
            
            # Draw dragging display on top if any
            if dragging_info is not None:
                idx, info = dragging_info
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
        
        # Determine fill color based on primary status only
        if display.get('primary'):
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
        
        # Draw border - use accent color if dragging
        if idx == self.dragging_display_idx:
            # Try to get system accent color
            accent_color = self._get_accent_color()
            if accent_color:
                cr.set_source_rgb(*accent_color)
            else:
                cr.set_source_rgb(0.2, 0.4, 0.8)  # Fallback to blue
        else:
            cr.set_source_rgb(0.1, 0.1, 0.1)
        
        cr.set_line_width(3)
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
        display_name = f"{name} ★" if display.get('primary') else name
        pango_layout.set_text(f"{display_name}\n{resolution}", -1)
        font_desc = Pango.FontDescription.new()
        font_desc.set_size(10 * 1024)  # Pango units
        pango_layout.set_font_description(font_desc)
        
        cr.move_to(x + 8, y + 8)
        PangoCairo.show_layout(cr, pango_layout)
    
    def _calculate_display_positions(self, canvas_width: int, canvas_height: int) -> List[Dict[str, Any]]:
        """
        Calculate positions and sizes for all displays on the canvas.
        Maintains aspect ratios and arranges them visually, centered in the canvas.
        
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
        
        # Calculate scaled display bounding box
        scaled_width = total_width * scale
        scaled_height = total_height * scale
        
        # Center the display arrangement in the canvas
        center_x = (canvas_width - scaled_width) / 2
        center_y = (canvas_height - scaled_height) / 2
        
        # Ensure minimum padding
        center_x = max(center_x, self.CANVAS_PADDING)
        center_y = max(center_y, self.CANVAS_PADDING)
        
        # Draw each display
        for arr_idx, arrangement in enumerate(self.arrangement):
            display = next((d for d in self.displays if d['connector'] == arrangement['connector']), None)
            if not display:
                continue
            
            # Calculate position relative to bounding box
            rel_x = arrangement['x'] - min_x
            rel_y = arrangement['y'] - min_y
            
            # Scale and offset to canvas (centered)
            canvas_x = center_x + (rel_x * scale)
            canvas_y = center_y + (rel_y * scale)
            
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
                self.last_drag_x = x
                self.last_drag_y = y
                # Save the initial arrangement position
                arr_idx = info['arrangement_idx']
                self.drag_start_arr_x = self.arrangement[arr_idx]['x']
                self.drag_start_arr_y = self.arrangement[arr_idx]['y']
                self.drag_arrangement_idx = arr_idx
                # Store render info for coordinate conversion
                self.drag_render_info = info
                logger.debug(f"Start dragging display {idx} from ({x}, {y})")
                self.queue_draw()
                break
    
    def _on_button_released(self, gesture, button, x, y):
        """Handle mouse button release"""
        if self.dragging_display_idx is not None:
            # Resolve overlaps AFTER releasing (allow overlaps during drag)
            if hasattr(self, 'drag_arrangement_idx'):
                arr_idx = self.drag_arrangement_idx
                cur_x = self.arrangement[arr_idx]['x']
                cur_y = self.arrangement[arr_idx]['y']
                new_x, new_y = self._resolve_all_collisions(arr_idx, cur_x, cur_y)
                self.arrangement[arr_idx]['x'] = new_x
                self.arrangement[arr_idx]['y'] = new_y
            
            logger.debug(f"Stopped dragging display {self.dragging_display_idx}")
            self.dragging_display_idx = None
            
            # Notify that arrangement has changed
            if self.on_arrangement_changed:
                self.on_arrangement_changed()
            
            self.queue_draw()
    
    def _on_mouse_motion(self, controller, x, y):
        """Handle mouse motion for dragging"""
        if self.dragging_display_idx is not None and hasattr(self, 'drag_render_info'):
            # Calculate ABSOLUTE delta from drag start (not incremental!)
            # This prevents drift from accumulating rounding errors
            total_delta_x = x - self.drag_start_x
            total_delta_y = y - self.drag_start_y
            
            # Convert canvas delta to world coordinates using scale from drag start
            scale = self.drag_render_info['scale_factor']
            world_delta_x = total_delta_x / scale
            world_delta_y = total_delta_y / scale
            
            # Snap to grid but keep precision
            snapped_x = round(world_delta_x / self.GRID_SIZE) * self.GRID_SIZE
            snapped_y = round(world_delta_y / self.GRID_SIZE) * self.GRID_SIZE
            
            # Update arrangement: set absolute position from start
            if hasattr(self, 'drag_arrangement_idx'):
                arr_idx = self.drag_arrangement_idx
                new_x = self.drag_start_arr_x + snapped_x
                new_y = self.drag_start_arr_y + snapped_y
                
                # Apply edge snapping during drag to nearest neighbor
                # Allow overlaps during drag - will be resolved on release
                new_x, new_y = self._snap_to_nearest_during_drag(arr_idx, new_x, new_y)
                
                self.arrangement[arr_idx]['x'] = new_x
                self.arrangement[arr_idx]['y'] = new_y
            
            # Update cursor
            self.set_cursor(Gdk.Cursor.new_from_name("grab"))
            
            self.queue_draw()
    
    def _snap_to_nearest_during_drag(self, dragging_idx: int, current_x: float, current_y: float) -> Tuple[float, float]:
        """
        Lightweight snapping during drag to nearest neighbor.
        Only snaps to the CLOSEST display to prevent switching.
        """
        dragging = self.arrangement[dragging_idx]
        dragging_w = dragging['physical_width']
        dragging_h = dragging['physical_height']
        
        best_x_snap = current_x
        best_y_snap = current_y
        best_x_dist = float('inf')
        best_y_dist = float('inf')
        
        for idx, other in enumerate(self.arrangement):
            if idx == dragging_idx:
                continue
            
            other_x = other['x']
            other_y = other['y']
            other_w = other['physical_width']
            other_h = other['physical_height']
            other_right = other_x + other_w
            other_bottom = other_y + other_h
            
            # Check horizontal alignment candidates
            h_candidates = [
                (abs(current_x - other_right), other_right),  # left to right
                (abs((current_x + dragging_w) - other_x), other_x - dragging_w),  # right to left
                (abs(current_x - other_x), other_x),  # left align
                (abs((current_x + dragging_w) - other_right), other_right - dragging_w),  # right align
            ]
            
            for dist, snap_val in h_candidates:
                if dist < self.SNAP_DISTANCE and dist < best_x_dist:
                    best_x_dist = dist
                    best_x_snap = snap_val
            
            # Check vertical alignment candidates
            v_candidates = [
                (abs(current_y - other_bottom), other_bottom),  # top to bottom
                (abs((current_y + dragging_h) - other_y), other_y - dragging_h),  # bottom to top
                (abs(current_y - other_y), other_y),  # top align
                (abs((current_y + dragging_h) - other_bottom), other_bottom - dragging_h),  # bottom align
            ]
            
            for dist, snap_val in v_candidates:
                if dist < self.SNAP_DISTANCE and dist < best_y_dist:
                    best_y_dist = dist
                    best_y_snap = snap_val
        
        return best_x_snap, best_y_snap
    
    def _snap_to_edges(self, dragging_idx: int):
        """
        Snap and collision detection for post-drag finalization.
        Only runs AFTER drag is complete (on release).
        """
        dragging = self.arrangement[dragging_idx]
        new_x = dragging['x']
        new_y = dragging['y']
        dragging_w = dragging['physical_width']
        dragging_h = dragging['physical_height']
        
        # First: prevent ALL overlaps
        new_x, new_y = self._resolve_all_collisions(dragging_idx, new_x, new_y)
        
        # Then: snap to nearest neighbor if close
        new_x, new_y = self._snap_to_nearest(dragging_idx, new_x, new_y)
        
        # Finally: resolve any overlaps created by snapping
        new_x, new_y = self._resolve_all_collisions(dragging_idx, new_x, new_y)
        
        # Update arrangement
        self.arrangement[dragging_idx]['x'] = int(new_x)
        self.arrangement[dragging_idx]['y'] = int(new_y)
    
    def _resolve_all_collisions(self, dragging_idx: int, new_x: float, new_y: float) -> Tuple[float, float]:
        """
        Resolve overlaps by pushing display away from ALL colliding neighbors.
        Keeps pushing until no overlaps remain.
        """
        dragging = self.arrangement[dragging_idx]
        dragging_w = dragging['physical_width']
        dragging_h = dragging['physical_height']
        
        # Keep checking until no overlaps
        max_iterations = 10
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            found_overlap = False
            
            new_right = new_x + dragging_w
            new_bottom = new_y + dragging_h
            
            # Check against all other displays
            for idx, other in enumerate(self.arrangement):
                if idx == dragging_idx:
                    continue
                
                other_x = other['x']
                other_y = other['y']
                other_w = other['physical_width']
                other_h = other['physical_height']
                other_right = other_x + other_w
                other_bottom = other_y + other_h
                
                # Check for overlap
                if (new_x < other_right and new_right > other_x and
                    new_y < other_bottom and new_bottom > other_y):
                    
                    found_overlap = True
                    
                    # Calculate overlap amounts in each direction
                    overlap_left = other_right - new_x  # How far to push right
                    overlap_right = new_right - other_x  # How far to push left
                    overlap_top = other_bottom - new_y  # How far to push down
                    overlap_bottom = new_bottom - other_y  # How far to push up
                    
                    # Find easiest direction to resolve (minimum push)
                    min_overlap = min(overlap_left, overlap_right, overlap_top, overlap_bottom)
                    
                    # Push in that direction
                    if min_overlap == overlap_left:
                        new_x = other_right
                    elif min_overlap == overlap_right:
                        new_x = other_x - dragging_w
                    elif min_overlap == overlap_top:
                        new_y = other_bottom
                    else:
                        new_y = other_y - dragging_h
                    
                    # Break and re-check from the beginning
                    break
            
            if not found_overlap:
                break
        
        return new_x, new_y
    
    def _snap_to_nearest(self, dragging_idx: int, current_x: float, current_y: float) -> Tuple[float, float]:
        """
        Snap to the single nearest neighbor within SNAP_DISTANCE.
        Only snaps to ONE neighbor (the closest).
        """
        dragging = self.arrangement[dragging_idx]
        dragging_w = dragging['physical_width']
        dragging_h = dragging['physical_height']
        
        # Find nearest neighbor
        nearest = None
        nearest_dist = float('inf')
        
        for idx, other in enumerate(self.arrangement):
            if idx == dragging_idx:
                continue
            
            other_x = other['x']
            other_y = other['y']
            other_w = other['physical_width']
            other_h = other['physical_height']
            other_right = other_x + other_w
            other_bottom = other_y + other_h
            
            # Euclidean distance from display edges
            dx = max(0,
                    (current_x - other_right) if current_x > other_right else 0,
                    (other_x - (current_x + dragging_w)) if other_x > (current_x + dragging_w) else 0)
            dy = max(0,
                    (current_y - other_bottom) if current_y > other_bottom else 0,
                    (other_y - (current_y + dragging_h)) if other_y > (current_y + dragging_h) else 0)
            
            dist = (dx ** 2 + dy ** 2) ** 0.5
            
            if dist < nearest_dist:
                nearest_dist = dist
                nearest = (other_x, other_y, other_w, other_h, other_right, other_bottom)
        
        if nearest is None or nearest_dist >= self.SNAP_DISTANCE:
            return current_x, current_y
        
        other_x, other_y, other_w, other_h, other_right, other_bottom = nearest
        
        # Snap to nearest edge
        snap_x = current_x
        snap_y = current_y
        
        # Horizontal snaps
        h_snaps = [
            (abs(current_x - other_right), other_right),  # left to right
            (abs((current_x + dragging_w) - other_x), other_x - dragging_w),  # right to left
            (abs(current_x - other_x), other_x),  # left align
            (abs((current_x + dragging_w) - other_right), other_right - dragging_w),  # right align
        ]
        
        h_snaps.sort()
        if h_snaps[0][0] < self.SNAP_DISTANCE:
            snap_x = h_snaps[0][1]
        
        # Vertical snaps
        v_snaps = [
            (abs(current_y - other_bottom), other_bottom),  # top to bottom
            (abs((current_y + dragging_h) - other_y), other_y - dragging_h),  # bottom to top
            (abs(current_y - other_y), other_y),  # top align
            (abs((current_y + dragging_h) - other_bottom), other_bottom - dragging_h),  # bottom align
        ]
        
        v_snaps.sort()
        if v_snaps[0][0] < self.SNAP_DISTANCE:
            snap_y = v_snaps[0][1]
        
        return snap_x, snap_y


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
        
        # Track original state for change detection
        self.original_arrangement = None
        
        # Canvas in a scrolled window for responsiveness
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_min_content_width(600)
        scroll.set_min_content_height(300)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
        
        self.canvas = ScreenArrangementCanvas()
        self.canvas.set_size_request(800, 400)  # Minimum drawing area size
        # Hook up callback for when arrangement changes
        self.canvas.on_arrangement_changed = self._update_button_states
        scroll.set_child(self.canvas)
        self.append(scroll)
        
        # Button box
        button_box = Gtk.Box(spacing=6)
        button_box.set_halign(Gtk.Align.END)
        
        # Reset button - disabled by default
        self.reset_btn = Gtk.Button(label="Reset")
        self.reset_btn.set_sensitive(False)
        self.reset_btn.connect("clicked", self._on_reset_clicked)
        button_box.append(self.reset_btn)
        
        # Apply button - disabled by default
        self.apply_btn = Gtk.Button(label="Apply Configuration")
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.set_sensitive(False)
        self.apply_btn.connect("clicked", self._on_apply_clicked)
        button_box.append(self.apply_btn)
        
        self.append(button_box)
    
    def set_displays(self, displays: List[Dict[str, Any]]):
        """Set the displays to arrange"""
        self.canvas.set_displays(displays)
        # Store original arrangement for change detection
        self.original_arrangement = [arr.copy() for arr in self.canvas.get_arrangement()]
        self._update_button_states()
    
    def _has_changes(self) -> bool:
        """Check if the current arrangement differs from the original"""
        if self.original_arrangement is None:
            return False
        
        current = self.canvas.get_arrangement()
        
        if len(current) != len(self.original_arrangement):
            return True
        
        # Compare key position and primary status
        for curr, orig in zip(current, self.original_arrangement):
            if (curr.get('x') != orig.get('x') or 
                curr.get('y') != orig.get('y') or
                curr.get('primary') != orig.get('primary')):
                return True
        
        return False
    
    def _update_button_states(self):
        """Update button sensitivity based on whether changes have been made"""
        has_changes = self._has_changes()
        self.apply_btn.set_sensitive(has_changes)
        self.reset_btn.set_sensitive(has_changes)
    
    def get_arrangement(self) -> List[Dict[str, Any]]:
        """Get the current arrangement"""
        return self.canvas.get_arrangement()
    
    def _on_reset_clicked(self, button):
        """Reset arrangement to original positions"""
        # Reload from displays
        self.canvas.set_displays(self.canvas.displays)
        self._update_button_states()
        logger.debug("Reset display arrangement")
    
    def _on_apply_clicked(self, button):
        """Emit signal to apply arrangement"""
        self.emit("apply-arrangement", self.get_arrangement())
    
    def update_original_arrangement(self):
        """Update the original arrangement after successful apply"""
        self.original_arrangement = [arr.copy() for arr in self.canvas.get_arrangement()]
        self._update_button_states()
        logger.debug("Updated original arrangement after successful apply")
    
    def do_apply_arrangement(self, arrangement):
        """Default implementation - override in subclass if needed"""
        pass
