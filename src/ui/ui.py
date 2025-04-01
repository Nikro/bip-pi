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
import sdl2.sdlttf

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
RED = sdl2.ext.Color(255, 0, 0)

# Font paths - using system fonts for better compatibility
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
MONO_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

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
    """Container for UI assets with proper text rendering and optimized animations."""
    
    def __init__(self, screen_width: int, screen_height: int, renderer):
        """Initialize and pre-render UI assets once to avoid runtime overhead."""
        self.renderer = renderer
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        # Calculate dimensions for animation panel
        self.animation_size = min(screen_width, screen_height // 2) - 40
        
        # Initialize SDL2 TTF for proper text rendering
        if sdl2.sdlttf.TTF_Init() != 0:
            logger.error(f"TTF initialization error: {sdl2.sdlttf.TTF_GetError().decode()}")
        
        # Load fonts with appropriate sizes
        font_scale = max(0.6, min(screen_width, screen_height) / 640)
        self.title_font_size = int(24 * font_scale)
        self.text_font_size = int(16 * font_scale)
        self.small_font_size = int(12 * font_scale)
        
        # Try to load system fonts, fallback if not available
        try:
            self.title_font = sdl2.sdlttf.TTF_OpenFont(FONT_PATH.encode(), self.title_font_size)
            self.text_font = sdl2.sdlttf.TTF_OpenFont(FONT_PATH.encode(), self.text_font_size)
            self.small_font = sdl2.sdlttf.TTF_OpenFont(MONO_FONT_PATH.encode(), self.small_font_size)
            
            if not self.title_font or not self.text_font or not self.small_font:
                logger.warning(f"Font loading error: {sdl2.sdlttf.TTF_GetError().decode()}")
                self._fallback_font_init()
        except Exception as e:
            logger.error(f"Error loading fonts: {e}")
            self._fallback_font_init()
            
        # Pre-render animation frames (RED for efficiency as requested)
        self.animation_frames = self._create_animation_frames(RED, 10)
    
    def _fallback_font_init(self):
        """Initialize fallback fonts if system fonts are unavailable."""
        # Scan for any available fonts in common locations
        font_dirs = [
            "/usr/share/fonts/truetype",
            "/usr/share/fonts/TTF",
            "/usr/share/fonts"
        ]
        
        font_found = False
        for font_dir in font_dirs:
            if not os.path.exists(font_dir):
                continue
                
            for root, _, files in os.walk(font_dir):
                for file in files:
                    if file.endswith(".ttf") and not font_found:
                        font_path = os.path.join(root, file)
                        logger.info(f"Using fallback font: {font_path}")
                        
                        self.title_font = sdl2.sdlttf.TTF_OpenFont(font_path.encode(), self.title_font_size)
                        self.text_font = sdl2.sdlttf.TTF_OpenFont(font_path.encode(), self.text_font_size)
                        self.small_font = sdl2.sdlttf.TTF_OpenFont(font_path.encode(), self.small_font_size)
                        
                        if self.title_font and self.text_font and self.small_font:
                            font_found = True
                            break
                
                if font_found:
                    break
            
            if font_found:
                break
    
    def _create_animation_frames(self, color, num_frames):
        """Pre-render animation frames for better performance."""
        frames = []
        animation_size = self.animation_size
        
        for i in range(num_frames):
            # Calculate pulse factor (0.7 to 1.0)
            pulse_factor = 0.7 + 0.3 * abs(num_frames/2 - i) / (num_frames/2)
            
            # Create surface for this frame
            surface = sdl2.SDL_CreateRGBSurface(
                0, animation_size, animation_size, 32,
                0xFF000000, 0x00FF0000, 0x0000FF00, 0x000000FF
            )
            
            # Fill with black (transparent background)
            sdl2.SDL_FillRect(
                surface, None, 
                sdl2.SDL_MapRGBA(surface.contents.format, 0, 0, 0, 0)
            )
            
            # Calculate circle parameters
            radius = int(animation_size // 2.5 * pulse_factor)
            center_x = animation_size // 2
            center_y = animation_size // 2
            
            # Draw filled circle
            self._draw_circle(surface, center_x, center_y, radius, color)
            
            # Create texture from surface
            texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, surface)
            frames.append(texture)
            
            # Free surface
            sdl2.SDL_FreeSurface(surface)
        
        return frames
    
    def _draw_circle(self, surface, x, y, radius, color):
        """Draw a circle with better visibility and efficiency."""
        # Get format-specific color mapping
        color_val = sdl2.SDL_MapRGBA(
            surface.contents.format, color.r, color.g, color.b, 255
        )
        
        # More efficient circle drawing algorithm that fills from inside out
        r_squared = radius * radius
        for dy in range(-radius, radius + 1):
            dx_max = int((r_squared - dy * dy) ** 0.5)
            for dx in range(-dx_max, dx_max + 1):
                sdl2.SDL_SetRenderDrawColor(self.renderer, color.r, color.g, color.b, 255)
                pos_x = x + dx
                pos_y = y + dy
                
                # Draw only if in bounds
                if 0 <= pos_x < surface.contents.w and 0 <= pos_y < surface.contents.h:
                    pixel_offset = pos_y * surface.contents.pitch + pos_x * 4
                    ctypes.memmove(
                        surface.contents.pixels + pixel_offset, 
                        ctypes.byref(ctypes.c_uint32(color_val)), 
                        4
                    )
    
    def render_text(self, text: str, font_type: str, x: int, y: int, color: sdl2.ext.Color) -> None:
        """
        Render text using SDL_ttf for proper font rendering.
        
        Args:
            text: Text to render
            font_type: Font type ("title", "text", or "small")
            x: X position
            y: Y position
            color: Text color
        """
        # Select font based on type
        if font_type == "title":
            font = self.title_font
        elif font_type == "text":
            font = self.text_font
        elif font_type == "small":
            font = self.small_font
        else:
            return
        
        # Create SDL color
        sdl_color = sdl2.SDL_Color(r=color.r, g=color.g, b=color.b, a=color.a)
        
        # Render text to surface (solid rendering for better performance)
        text_surface = sdl2.sdlttf.TTF_RenderText_Solid(
            font, text.encode(), sdl_color
        )
        
        if not text_surface:
            return
        
        # Create texture from surface
        text_texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, text_surface)
        
        # Setup destination rectangle
        text_rect = sdl2.SDL_Rect(
            x=x, y=y,
            w=text_surface.contents.w,
            h=text_surface.contents.h
        )
        
        # Render texture to screen
        sdl2.SDL_RenderCopy(self.renderer, text_texture, None, text_rect)
        
        # Free resources
        sdl2.SDL_FreeSurface(text_surface)
        sdl2.SDL_DestroyTexture(text_texture)
    
    def cleanup(self):
        """Clean up resources to prevent memory leaks."""
        # Close fonts
        if hasattr(self, 'title_font') and self.title_font:
            sdl2.sdlttf.TTF_CloseFont(self.title_font)
        
        if hasattr(self, 'text_font') and self.text_font:
            sdl2.sdlttf.TTF_CloseFont(self.text_font)
        
        if hasattr(self, 'small_font') and self.small_font:
            sdl2.sdlttf.TTF_CloseFont(self.small_font)
        
        # Clean up TTF subsystem
        sdl2.sdlttf.TTF_Quit()


class UINode:
    """Main UI node class with optimizations for low-end hardware."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the optimized UI node."""
        # Load configuration
        self.config = load_config(config_path) if config_path else {}
        
        # Initialize SDL2
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO) != 0:
            logger.error(f"SDL initialization error: {sdl2.SDL_GetError().decode()}")
            sys.exit(1)
        
        # Get display info
        display_mode = sdl2.SDL_DisplayMode()
        sdl2.SDL_GetCurrentDisplayMode(0, ctypes.byref(display_mode))
        
        # Default UI settings
        self.width = self.config.get("ui", {}).get("width", display_mode.w)
        self.height = self.config.get("ui", {}).get("height", display_mode.h)
        self.fps = self.config.get("ui", {}).get("fps", 30)
        self.fullscreen = self.config.get("ui", {}).get("fullscreen", True)
        
        logger.info(f"Display resolution: {self.width}x{self.height}")
        
        # Initialize state
        self.state = global_state
        self.state.show_debug = True
        
        # Create window and renderer with hardware acceleration
        flags = sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP if self.fullscreen else 0
        self.window = sdl2.SDL_CreateWindow(
            b"Reactive Companion",
            sdl2.SDL_WINDOWPOS_CENTERED,
            sdl2.SDL_WINDOWPOS_CENTERED,
            self.width, self.height, flags
        )
        
        if not self.window:
            logger.error(f"Window creation error: {sdl2.SDL_GetError().decode()}")
            sys.exit(1)
        
        # Get actual window size (in case of fullscreen)
        window_surface = sdl2.SDL_GetWindowSurface(self.window)
        if window_surface:
            self.width = window_surface.contents.w
            self.height = window_surface.contents.h
        
        # Create renderer with vsync for smooth animation
        self.renderer = sdl2.SDL_CreateRenderer(
            self.window, -1, 
            sdl2.SDL_RENDERER_ACCELERATED | sdl2.SDL_RENDERER_PRESENTVSYNC
        )
        
        if not self.renderer:
            logger.error(f"Renderer creation error: {sdl2.SDL_GetError().decode()}")
            sys.exit(1)
        
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
        
        # Stop monitoring thread
        if hasattr(self, 'monitor'):
            self.monitor.running = False
        
        # Clean up assets
        if hasattr(self, 'assets'):
            self.assets.cleanup()
        
        # Clean up SDL2
        if hasattr(self, 'renderer') and self.renderer:
            sdl2.SDL_DestroyRenderer(self.renderer)
        
        if hasattr(self, 'window') and self.window:
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
                    flags = sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP if self.fullscreen else 0
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
        """Render the top panel with pulsating red circle."""
        # Get current animation frame
        animation_frame = self.assets.animation_frames[self.current_frame]
        
        # Center the animation in the top panel
        dest_rect = sdl2.SDL_Rect(
            (self.width - self.assets.animation_size) // 2,
            (self.top_panel_height - self.assets.animation_size) // 2,
            self.assets.animation_size,
            self.assets.animation_size
        )
        
        # Render the animation frame
        sdl2.SDL_RenderCopy(self.renderer, animation_frame, None, dest_rect)
    
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
            "title",
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
            f"Temperature: {self.monitor.temperature:.1f}°C"
        ]
        
        for info in status_info:
            self.assets.render_text(
                info,
                "text",
                20,
                y_pos,
                LIGHT_GRAY
            )
            y_pos += self.assets.text_font_size + 5
    
    def _render_debug(self) -> None:
        """Render debug information in the bottom-right corner."""
        if not self.state.show_debug:
            return
        
        # Debug information
        debug_info = [
            f"FPS: {self.state.fps}",
            f"CPU: {self.monitor.cpu_usage:.1f}%",
            f"MEM: {self.monitor.memory_usage:.1f}MB",
            f"TEMP: {self.monitor.temperature:.1f}°C",
            f"Resolution: {self.width}x{self.height}"
        ]
        
        # Draw semi-transparent background (right-aligned)
        bg_width = 180
        bg_height = (len(debug_info) * (self.assets.small_font_size + 5)) + 10
        
        bg_rect = sdl2.SDL_Rect(
            self.width - bg_width - 10,
            self.height - bg_height - 10,
            bg_width,
            bg_height
        )
        
        # Set semi-transparent black
        sdl2.SDL_SetRenderDrawColor(self.renderer, 0, 0, 0, 180)
        sdl2.SDL_RenderFillRect(self.renderer, bg_rect)
        
        # Draw border
        sdl2.SDL_SetRenderDrawColor(self.renderer, GRAY.r, GRAY.g, GRAY.b, GRAY.a)
        sdl2.SDL_RenderDrawRect(self.renderer, bg_rect)
        
        # Render each line of debug info
        for i, info in enumerate(debug_info):
            self.assets.render_text(
                info,
                "small",
                self.width - bg_width,
                self.height - bg_height + (i * (self.assets.small_font_size + 5)) + 5,
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
