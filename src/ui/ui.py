"""
UI node for the reactive companion system using a lightweight rendering approach.

This implementation uses PyGame for better compatibility and optimization for 
resource-constrained hardware like the Orange Pi.
"""

import argparse
import os
import sys
import time
import threading
from typing import Dict, Any, List, Tuple, Optional

# Import PyGame - more compatible and easier to optimize than direct SDL2
import pygame

from ..common import (
    setup_logger, PublisherBase, SubscriberBase, RequestorBase,
    DEFAULT_PORTS, MessageType, safe_execute, load_config
)
from .state import UIState, SystemMode, global_state

# Setup logger
logger = setup_logger("ui")

# Define colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (128, 128, 128)
LIGHT_GRAY = (200, 200, 200)
RED = (255, 0, 0)

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
    
    def __init__(self, screen_width: int, screen_height: int):
        """Initialize and pre-render UI assets once to avoid runtime overhead."""
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        # Calculate dimensions for animation panel - much smaller circle (10x smaller)
        self.animation_size = min(screen_width, screen_height // 2) // 5
        
        # Load fonts with appropriate sizes
        font_scale = max(0.6, min(screen_width, screen_height) / 640)
        self.title_font_size = int(24 * font_scale)
        self.text_font_size = int(16 * font_scale)
        self.small_font_size = int(10 * font_scale)  # Smaller debug text
        
        # Try to load system fonts, fallback if not available
        try:
            self.title_font = pygame.font.Font(FONT_PATH, self.title_font_size)
            self.text_font = pygame.font.Font(FONT_PATH, self.text_font_size)
            self.small_font = pygame.font.Font(MONO_FONT_PATH, self.small_font_size)
        except Exception as e:
            logger.error(f"Error loading fonts: {e}")
            self._fallback_font_init()
            
        # Pre-render animation frames (efficient as requested)
        self.animation_frames = self._create_animation_frames(RED, 10)
    
    def _fallback_font_init(self):
        """Initialize fallback fonts if system fonts are unavailable."""
        # Use PyGame's built-in fonts as fallback
        self.title_font = pygame.font.SysFont("sans", self.title_font_size)
        self.text_font = pygame.font.SysFont("sans", self.text_font_size)
        self.small_font = pygame.font.SysFont("monospace", self.small_font_size)
    
    def _create_animation_frames(self, color, num_frames):
        """Pre-render animation frames for better performance with more subtle animation."""
        frames = []
        animation_size = self.animation_size
        
        for i in range(num_frames):
            # Calculate even more subtle pulse factor (0.92 to 1.0 for very subtle animation)
            pulse_factor = 0.92 + 0.08 * abs(num_frames/2 - i) / (num_frames/2)
            
            # Create surface for this frame (with solid background)
            surface = pygame.Surface((animation_size, animation_size))
            surface.fill(BLACK)  # Solid black background
            
            # Calculate circle parameters
            radius = int(animation_size // 2.5 * pulse_factor)
            center_x = animation_size // 2
            center_y = animation_size // 2
            
            # Draw filled circle
            pygame.draw.circle(surface, color, (center_x, center_y), radius)
            
            # Store the surface
            frames.append(surface)
        
        return frames
    
    def render_text(self, surface, text: str, font_type: str, x: int, y: int, 
                   color) -> None:
        """
        Render text efficiently.
        
        Args:
            surface: Surface to render on
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
        
        # Pre-render text to a surface (solid for best performance)
        text_surface = font.render(text, True, color)
        
        # Blit to destination
        surface.blit(text_surface, (x, y))
        
        # No need to return anything since we're modifying the provided surface


class UINode:
    """Main UI node class with optimizations for low-end hardware."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the optimized UI node."""
        # Load configuration
        self.config = load_config(config_path) if config_path else {}
        
        # Initialize PyGame
        pygame.init()
        
        # Get display info
        pygame.display.init()
        info = pygame.display.Info()
        
        # Default UI settings
        self.width = self.config.get("ui", {}).get("width", info.current_w)
        self.height = self.config.get("ui", {}).get("height", info.current_h)
        self.fps = self.config.get("ui", {}).get("fps", 30)
        self.fullscreen = self.config.get("ui", {}).get("fullscreen", True)
        
        logger.info(f"Display resolution: {self.width}x{self.height}")
        
        # Initialize state
        self.state = global_state
        self.state.show_debug = True
        
        # Create window with hardware acceleration
        flags = pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF if self.fullscreen else pygame.HWSURFACE | pygame.DOUBLEBUF
        self.screen = pygame.display.set_mode((self.width, self.height), flags)
        pygame.display.set_caption("Reactive Companion")
        
        # Get actual window size (in case of fullscreen)
        self.width, self.height = self.screen.get_size()
        
        # Create subsurfaces for partial updates
        self.top_panel_height = self.height // 2
        self.top_surface = self.screen.subsurface((0, 0, self.width, self.top_panel_height))
        self.bottom_surface = self.screen.subsurface((0, self.top_panel_height, 
                                                     self.width, self.height - self.top_panel_height))
        
        # Load assets
        self.assets = UIAssets(self.width, self.height)
        
        # Create background monitor thread
        self.monitor = BackgroundMonitor(self)
        self.monitor.start()
        
        # Communication setup
        self.publisher = PublisherBase(DEFAULT_PORTS["ui_pub"])
        self.subscriber = SubscriberBase("localhost", DEFAULT_PORTS["awareness_pub"])
        
        # Animation state
        self.current_frame = 0
        self.frame_count = 0
        self.bottom_update_counter = 0  # Counter for bottom panel updates
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
        
        # Clean up PyGame
        pygame.quit()
        
        logger.info("UI node stopped")
    
    def _main_loop(self) -> None:
        """Optimized main loop for better performance."""
        clock = pygame.time.Clock()
        
        # Initial full screen draw
        self.top_surface.fill(BLACK)
        self.bottom_surface.fill(BLACK)
        self._render_top_panel()
        self._render_bottom_panel()
        self._render_debug()
        pygame.display.flip()  # Ensure a full screen update initially
        
        while self.is_running:
            # Handle events
            self._process_events()
            
            # Check for messages (non-blocking)
            self._check_messages()
            
            # Update animation state
            self._update_animation()
            
            # Clear top panel and redraw (frequent updates)
            self.top_surface.fill(BLACK)
            self._render_top_panel()
            
            # Update bottom panel less frequently (every 10 frames)
            self.bottom_update_counter += 1
            if self.bottom_update_counter >= 10:
                self.bottom_surface.fill(BLACK)
                self._render_bottom_panel()
                
                # Render debug if enabled
                if self.state.show_debug:
                    self._render_debug()
                    
                self.bottom_update_counter = 0
            
            # Update display - use flip() for complete redrawing to avoid tearing
            pygame.display.flip()
            
            # Update FPS counter
            self.frame_count += 1
            current_time = time.time()
            if current_time - self.last_frame_time >= 1.0:
                self.state.fps = self.frame_count
                self.frame_count = 0
                self.last_frame_time = current_time
            
            # Limit frame rate
            clock.tick(self.fps)
    
    def _process_events(self) -> None:
        """Process PyGame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.is_running = False
            
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # Escape key exits
                    self.is_running = False
                
                elif event.key == pygame.K_d:
                    # Toggle debug mode
                    self.state.show_debug = not self.state.show_debug
                
                elif event.key == pygame.K_f:
                    # Toggle fullscreen
                    self.fullscreen = not self.fullscreen
                    flags = pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF if self.fullscreen else pygame.HWSURFACE | pygame.DOUBLEBUF
                    self.screen = pygame.display.set_mode((self.width, self.height), flags)
                    
                    # Recreate subsurfaces after display mode change
                    self.top_surface = self.screen.subsurface((0, 0, self.width, self.top_panel_height))
                    self.bottom_surface = self.screen.subsurface((0, self.top_panel_height, 
                                                                self.width, self.height - self.top_panel_height))
    
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
        center_x = (self.width - self.assets.animation_size) // 2
        center_y = (self.top_panel_height - self.assets.animation_size) // 2
        
        # Create a rectangle for the area we're updating - only update the circle area
        update_rect = pygame.Rect(
            center_x, 
            center_y, 
            self.assets.animation_size, 
            self.assets.animation_size
        )
        
        # Clear only the area we're updating
        self.top_surface.fill(BLACK, update_rect)
        
        # Blit the pre-rendered animation frame
        self.top_surface.blit(animation_frame, (center_x, center_y))
    
    def _render_bottom_panel(self) -> None:
        """Render the bottom panel with information."""
        # Draw a separator line between panels
        pygame.draw.line(
            self.bottom_surface, 
            GRAY,
            (0, 0),
            (self.width, 0)
        )
        
        # Get the current mode
        mode = self.state.mode
        
        # Render mode text
        self.assets.render_text(
            self.bottom_surface,
            f"Mode: {mode.name}",
            "title",
            20, 
            20,
            WHITE
        )
        
        # Render additional status information
        y_pos = 20 + self.assets.title_font_size + 10
        
        # System status - removed "Last Update" line
        status_info = [
            f"System Status: Online",
            f"Temperature: {self.monitor.temperature:.1f}°C"
        ]
        
        for info in status_info:
            self.assets.render_text(
                self.bottom_surface,
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
            f"Res: {self.width}x{self.height}"  # Shortened text
        ]
        
        # Calculate dimensions for debug panel
        bg_width = 160  # Reduced width
        bg_height = (len(debug_info) * (self.assets.small_font_size + 5)) + 10
        
        # Draw solid background (right-aligned but moved left a bit)
        bg_rect = pygame.Rect(
            self.width - bg_width - 30,  # More padding on right side
            self.height - self.top_panel_height - bg_height - 10,
            bg_width,
            bg_height
        )
        
        # Draw background and border
        pygame.draw.rect(self.bottom_surface, BLACK, bg_rect)
        pygame.draw.rect(self.bottom_surface, GRAY, bg_rect, 1)  # 1px border
        
        # Render each line of debug info
        for i, info in enumerate(debug_info):
            self.assets.render_text(
                self.bottom_surface,
                info,
                "small",
                self.width - bg_width - 25,  # More padding on right side for text
                self.height - self.top_panel_height - bg_height + (i * (self.assets.small_font_size + 5)) + 5,
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
