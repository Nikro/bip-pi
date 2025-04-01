"""
UI node for the reactive companion system using a lightweight rendering approach.

This implementation uses direct SDL2 bindings through PySDL2 for better performance
on resource-constrained hardware like the Orange Pi.
"""

import argparse
import os
import sys
import time
import threading
from typing import Dict, Any, List, Tuple, Optional
import ctypes

# Import SDL2 library - a more direct and efficient graphics library than Pygame
import sdl2
import sdl2.ext
import sdl2.surface

from ..common import (
    setup_logger, PublisherBase, SubscriberBase, RequestorBase,
    DEFAULT_PORTS, MessageType, safe_execute, load_config
)
from .state import UIState, SystemMode, global_state

# Setup logger
logger = setup_logger("ui")

# Define colors
BLACK = sdl2.ext.Color(0, 0, 0)
WHITE = sdl2.ext.Color(255, 255, 255)
GRAY = sdl2.ext.Color(128, 128, 128)
LIGHT_GRAY = sdl2.ext.Color(200, 200, 200)
BLUE = sdl2.ext.Color(0, 0, 255)
LIGHT_BLUE = sdl2.ext.Color(100, 100, 255)
GREEN = sdl2.ext.Color(0, 255, 0)
RED = sdl2.ext.Color(255, 0, 0)

class BackgroundMonitor(threading.Thread):
    """Background thread for system monitoring tasks."""
    
    def __init__(self, ui_node):
        """Initialize the background monitor thread."""
        super().__init__(daemon=True)
        self.ui_node = ui_node
        self.running = True
        self.temperature = 0.0
        self.cpu_usage = 0.0
        self.memory_usage = 0.0
    
    def run(self):
        """Run the monitoring thread."""
        import psutil
        
        while self.running:
            # Update system metrics in a separate thread to avoid blocking the UI
            try:
                # Update temperature
                self.temperature = self._get_system_temperature()
                
                # Update CPU and memory usage
                self.cpu_usage = psutil.cpu_percent()
                self.memory_usage = psutil.virtual_memory().used / (1024 * 1024)  # Convert to MB
                
                # Update state in thread-safe manner
                self.ui_node.state.cpu_usage = self.cpu_usage
                self.ui_node.state.memory_usage = self.memory_usage
                
                # Sleep to reduce CPU usage
                time.sleep(1.0)
            except Exception as e:
                logger.error(f"Error in background monitor: {e}")
                time.sleep(1.0)
    
    def _get_system_temperature(self) -> float:
        """Get the current system temperature."""
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as temp_file:
                return float(temp_file.read().strip()) / 1000.0
        except (IOError, ValueError):
            try:
                import subprocess
                result = subprocess.run(
                    ["vcgencmd", "measure_temp"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    temp_str = result.stdout.strip()
                    return float(temp_str.split("=")[1].split("'")[0])
            except:
                pass
        return 0.0


class UIAssets:
    """Container for UI assets with pre-rendered animations for better performance."""
    
    def __init__(self, screen_width: int, screen_height: int, renderer):
        """Initialize and pre-render UI assets once to avoid runtime overhead."""
        self.renderer = renderer
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.factory = sdl2.ext.SpriteFactory(sdl2.ext.SOFTWARE)
        
        # Calculate dimensions for animation panel
        self.animation_size = min(screen_width, screen_height // 2) - 40
        
        # Create font resources - use smaller font sizes for better display
        font_scale = max(0.6, min(screen_width, screen_height) / 640)
        self.title_font_size = int(24 * font_scale)
        self.text_font_size = int(16 * font_scale)
        self.small_font_size = int(12 * font_scale)
        
        # Pre-render animation frames (only RED for efficiency as requested)
        self.animation_frames = self._create_animation_frames(RED, 5)  # Reduced to 5 frames for better performance
        
        # Pre-render font character map for faster text rendering
        self._init_bitmap_font()
    
    def _create_animation_frames(self, color, num_frames):
        """Pre-render animation frames for better performance."""
        frames = []
        animation_size = self.animation_size
        
        # Use simple circle animation without complex glow effects
        for i in range(num_frames):
            # Calculate pulse factor (0.7 to 1.0)
            pulse_factor = 0.7 + 0.3 * abs(num_frames/2 - i) / (num_frames/2)
            
            # Create surface for this frame
            surface = sdl2.SDL_CreateRGBSurface(0, animation_size, animation_size, 32, 
                                               0xFF000000, 0x00FF0000, 0x0000FF00, 0x000000FF)
            
            # Fill with black (transparent background)
            sdl2.SDL_FillRect(surface, None, sdl2.SDL_MapRGBA(surface.contents.format, 0, 0, 0, 0))
            
            # Draw circle
            radius = int(animation_size // 2.5 * pulse_factor)
            center_x = animation_size // 2
            center_y = animation_size // 2
            
            # Draw a simple filled circle - much faster than multiple transparent layers
            self._draw_filled_circle(surface, center_x, center_y, radius, 
                                    color.r, color.g, color.b, 255)
            
            # Create texture from surface
            texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, surface)
            frames.append(texture)
            sdl2.SDL_FreeSurface(surface)
            
        return frames
    
    def _draw_filled_circle(self, surface, x, y, radius, r, g, b, a):
        """Draw a filled circle using a more efficient algorithm."""
        # This is a simple and efficient circle drawing algorithm
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx*dx + dy*dy <= radius*radius:
                    sdl2.SDL_SetRenderDrawColor(self.renderer, r, g, b, a)
                    sdl2.SDL_RenderDrawPoint(self.renderer, x + dx, y + dy)
    
    def _init_bitmap_font(self) -> None:
        """Initialize a simple bitmap font for efficient text rendering."""
        # Create character maps for different font sizes
        self.char_maps = {}
        
        # Define character set (basic ASCII)
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:,.-_+*()[]{}|/\\%$#@!? "
        
        # Generate bitmap textures for each font size
        for size_name, pixel_size in [
            ("small", self.small_font_size),
            ("medium", self.text_font_size),
            ("large", self.title_font_size)
        ]:
            char_width = pixel_size // 2
            char_height = pixel_size
            
            # Create a map to store character textures
            self.char_maps[size_name] = {}
            
            # For each character, create a texture
            for char in chars:
                # Create a surface for this character
                surface = sdl2.SDL_CreateRGBSurface(
                    0, char_width, char_height, 32,
                    0xFF000000, 0x00FF0000, 0x0000FF00, 0x000000FF
                )
                
                # Fill with black (transparent background)
                sdl2.SDL_FillRect(
                    surface, None, 
                    sdl2.SDL_MapRGBA(surface.contents.format, 0, 0, 0, 0)
                )
                
                # Draw the character (simulated bitmap font)
                self._draw_character(surface, char, char_width, char_height)
                
                # Create texture from surface
                texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, surface)
                
                # Store in character map
                self.char_maps[size_name][char] = {
                    "texture": texture,
                    "width": char_width,
                    "height": char_height
                }
                
                # Free the surface
                sdl2.SDL_FreeSurface(surface)
    
    def _draw_character(self, surface, char: str, width: int, height: int) -> None:
        """Draw a single character on a surface using primitive shapes."""
        # Set white color for character pixels
        pixel_color = sdl2.SDL_MapRGBA(surface.contents.format, 255, 255, 255, 255)
        
        # Simple bitmap representation of characters
        # This is a very basic approach - each character is drawn with primitive rectangles
        
        # For this implementation, we'll use a simple dot matrix approach
        # More sophisticated bitmap fonts would use pre-designed patterns
        
        # Draw a rectangle for most characters (simplified approach)
        rect = sdl2.SDL_Rect(2, 2, width - 4, height - 4)
        sdl2.SDL_FillRect(surface, rect, pixel_color)
        
        # Draw a hole in certain characters
        if char in "ABDOPQRabdeopqg":
            hole_rect = sdl2.SDL_Rect(
                width // 3, height // 3, 
                width // 3, height // 3
            )
            sdl2.SDL_FillRect(
                surface, hole_rect, 
                sdl2.SDL_MapRGBA(surface.contents.format, 0, 0, 0, 0)
            )
    
    def render_text(self, text: str, size_name: str, x: int, y: int, color: sdl2.ext.Color) -> None:
        """
        Render text at the given position using the bitmap font.
        
        Args:
            text: The text to render
            size_name: Font size name ("small", "medium", or "large")
            x: X-coordinate for the text
            y: Y-coordinate for the text
            color: Text color
        """
        if size_name not in self.char_maps:
            return
        
        char_map = self.char_maps[size_name]
        current_x = x
        
        # Set the color modulation for the text
        for char in text:
            if char in char_map:
                char_data = char_map[char]
                texture = char_data["texture"]
                
                # Set color modulation
                sdl2.SDL_SetTextureColorMod(
                    texture, color.r, color.g, color.b
                )
                
                # Set alpha
                sdl2.SDL_SetTextureAlphaMod(texture, color.a)
                
                # Render the character
                dest_rect = sdl2.SDL_Rect(
                    current_x, y, 
                    char_data["width"], char_data["height"]
                )
                sdl2.SDL_RenderCopy(self.renderer, texture, None, dest_rect)
                
                # Move to the next character position
                current_x += char_data["width"]
            elif char == '\n':
                # Handle newline characters
                current_x = x
                y += char_map[' ']["height"] + 2
            else:
                # For characters not in our map, use a space
                current_x += char_map[' ']["width"]


class UINode:
    """Main UI node class with optimizations for low-end hardware."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the optimized UI node."""
        # Load configuration
        self.config = load_config(config_path) if config_path else {}
        
        # Initialize SDL2
        sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO)
        
        # Get display info
        display_mode = sdl2.SDL_DisplayMode()
        sdl2.SDL_GetCurrentDisplayMode(0, ctypes.byref(display_mode))
        
        # Default UI settings
        self.width = self.config.get("ui", {}).get("width", display_mode.w)
        self.height = self.config.get("ui", {}).get("height", display_mode.h)
        self.fps = self.config.get("ui", {}).get("fps", 30)  # Reduced FPS target for better performance
        self.fullscreen = self.config.get("ui", {}).get("fullscreen", True)
        
        logger.info(f"Display resolution: {self.width}x{self.height}")
        
        # Initialize state
        self.state = global_state
        self.state.show_debug = True
        
        # Create window and renderer with hardware acceleration
        flags = sdl2.SDL_WINDOW_FULLSCREEN if self.fullscreen else 0
        self.window = sdl2.SDL_CreateWindow(b"Reactive Companion",
                                          sdl2.SDL_WINDOWPOS_CENTERED,
                                          sdl2.SDL_WINDOWPOS_CENTERED,
                                          self.width, self.height, flags)
        
        self.renderer = sdl2.SDL_CreateRenderer(
            self.window, -1, 
            sdl2.SDL_RENDERER_ACCELERATED | sdl2.SDL_RENDERER_PRESENTVSYNC
        )
        
        # Define panel dimensions
        self.top_panel_height = self.height // 2
        
        # Load assets
        self.assets = UIAssets(self.width, self.height, self.renderer)
        
        # Create background monitor thread
        self.monitor = BackgroundMonitor(self)
        self.monitor.start()
        
        # Communication setup
        self.publisher = PublisherBase(DEFAULT_PORTS["ui_pub"])
        self.subscriber = SubscriberBase("localhost", DEFAULT_PORTS["awareness_pub"])
        
        # Animation state
        self.current_frame = 0
        self.frame_count = 0
        self.last_frame_time = time.time()
        self.frame_duration = 1.0 / self.fps
        
        # Running flag
        self.is_running = False
        logger.info(f"UI node initialized with resolution {self.width}x{self.height}")
    
    def start(self) -> None:
        """Start the UI node."""
        if self.is_running:
            logger.warning("UI node is already running")
            return
        
        self.is_running = True
        logger.info("UI node started")
        
        # Main loop
        try:
            self._main_loop()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Error in UI main loop: {str(e)}")
        finally:
            self.stop()
    
    def stop(self) -> None:
        """Stop the UI node and clean up resources."""
        self.is_running = False
        
        # Clean up SDL2
        sdl2.SDL_DestroyRenderer(self.renderer)
        sdl2.SDL_DestroyWindow(self.window)
        sdl2.SDL_Quit()
        
        logger.info("UI node stopped")
    
    def _main_loop(self) -> None:
        """Optimized main loop for better performance."""
        while self.is_running:
            # Start frame timing
            frame_start = time.time()
            
            # Handle events
            self._process_events()
            
            # Check for messages (non-blocking)
            self._check_messages()
            
            # Update animation state
            self._update_animation()
            
            # Clear screen
            sdl2.SDL_SetRenderDrawColor(self.renderer, 0, 0, 0, 255)
            sdl2.SDL_RenderClear(self.renderer)
            
            # Render UI elements
            self._render_top_panel()
            self._render_bottom_panel()
            
            # Render debug if enabled
            if self.state.show_debug:
                self._render_debug()
            
            # Present the frame
            sdl2.SDL_RenderPresent(self.renderer)
            
            # Update FPS counter
            self.frame_count += 1
            current_time = time.time()
            if current_time - self.last_frame_time >= 1.0:
                self.state.fps = self.frame_count
                self.frame_count = 0
                self.last_frame_time = current_time
            
            # Frame rate control
            frame_time = time.time() - frame_start
            if frame_time < self.frame_duration:
                time.sleep(self.frame_duration - frame_time)
    
    def _process_events(self) -> None:
        """Process SDL2 events."""
        events = sdl2.ext.get_events()
        for event in events:
            if event.type == sdl2.SDL_QUIT:
                self.is_running = False
            
            elif event.type == sdl2.SDL_KEYDOWN:
                if event.key.keysym.sym == sdl2.SDLK_ESCAPE:
                    # Escape key exits
                    self.is_running = False
                
                elif event.key.keysym.sym == sdl2.SDLK_d:
                    # Toggle debug mode
                    self.state.show_debug = not self.state.show_debug
                
                elif event.key.keysym.sym == sdl2.SDLK_f:
                    # Toggle fullscreen
                    self.fullscreen = not self.fullscreen
                    flags = sdl2.SDL_WINDOW_FULLSCREEN if self.fullscreen else 0
                    sdl2.SDL_SetWindowFullscreen(self.window, flags)
    
    def _check_messages(self) -> None:
        """Check for messages from other nodes."""
        # Non-blocking check for messages with a small timeout
        message = self.subscriber.receive(timeout=10)
        if message:
            # Update state based on the message
            self.state.update_from_message(message)
    
    def _update_animation(self) -> None:
        """Update animation state."""
        self.current_frame = (self.current_frame + 1) % len(self.assets.animation_frames)
    
    def _render_top_panel(self) -> None:
        """Render the top panel with animation."""
        # Get current animation frame
        animation_frame = self.assets.animation_frames[self.current_frame]
        
        # Center the animation in the top panel
        sdl2.SDL_RenderCopy(
            self.renderer, animation_frame, None, 
            sdl2.SDL_Rect(
                (self.width - self.assets.animation_size) // 2, 
                (self.top_panel_height - self.assets.animation_size) // 2, 
                self.assets.animation_size, self.assets.animation_size
            )
        )
    
    def _render_bottom_panel(self) -> None:
        """Render the bottom panel with information."""
        # Define the panel area
        panel_y = self.top_panel_height
        panel_height = self.height - self.top_panel_height
        
        # Draw a separator line between panels
        sdl2.SDL_SetRenderDrawColor(self.renderer, GRAY.r, GRAY.g, GRAY.b, GRAY.a)
        sdl2.SDL_RenderDrawLine(
            self.renderer, 
            0, self.top_panel_height,
            self.width, self.top_panel_height
        )
        
        # Get the current mode
        mode = self.state.mode
        
        # Render mode text
        self.assets.render_text(
            f"Mode: {mode.name}",
            "large",
            20, 
            panel_y + 20,
            WHITE
        )
        
        # Render additional status information
        y_pos = panel_y + 20 + self.assets.title_font_size + 10
        
        # System status
        status_info = [
            f"System Status: Online",
            f"Last Update: {time.strftime('%H:%M:%S')}",
            f"Uptime: {int(time.time() - self.last_frame_time)} seconds"
        ]
        
        for info in status_info:
            self.assets.render_text(
                info,
                "medium",
                20,
                y_pos,
                LIGHT_GRAY
            )
            y_pos += self.assets.text_font_size + 5
    
    def _render_debug(self) -> None:
        """Render debug information in the bottom-right corner."""
        if not self.state.show_debug:
            return
        
        # Get temperature from background monitor
        temp = self.monitor.temperature
        
        # Debug information
        debug_info = [
            f"FPS: {self.state.fps}",
            f"CPU: {self.monitor.cpu_usage:.1f}%",
            f"MEM: {self.monitor.memory_usage:.1f}MB",
            f"TEMP: {temp:.1f}C",
            f"Resolution: {self.width}x{self.height}"
        ]
        
        # Calculate position (bottom-right corner)
        longest_text = max(debug_info, key=len)
        text_width = len(longest_text) * (self.assets.small_font_size // 2)
        
        # Draw semi-transparent background
        bg_rect = sdl2.SDL_Rect(
            self.width - text_width - 30,
            self.height - (len(debug_info) * (self.assets.small_font_size + 5)) - 20,
            text_width + 20,
            (len(debug_info) * (self.assets.small_font_size + 5)) + 10
        )
        
        # Set semi-transparent black
        sdl2.SDL_SetRenderDrawColor(self.renderer, 0, 0, 0, 180)
        sdl2.SDL_RenderFillRect(self.renderer, bg_rect)
        
        # Render each line of debug info
        for i, info in enumerate(debug_info):
            self.assets.render_text(
                info,
                "small",
                self.width - text_width - 20,
                self.height - (len(debug_info) - i) * (self.assets.small_font_size + 5),
                LIGHT_GRAY
            )


def main() -> None:
    """Main entry point for the UI node."""
    parser = argparse.ArgumentParser(description="UI Node")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    args = parser.parse_args()
    
    # Create and start the UI node
    node = UINode(args.config)
    node.start()


if __name__ == "__main__":
    main()
