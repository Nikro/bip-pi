"""
UI node for the reactive companion system using a lightweight rendering approach.
"""

import argparse
import os
import sys
import time
import threading
import logging
from typing import Dict, Any, List, Tuple, Optional

# Simple direct import - no try/except that could cause scope issues
import pygame
from pygame.locals import FULLSCREEN, HWSURFACE, DOUBLEBUF, SRCALPHA, SCALED

from ..common import (
    setup_logger, PublisherBase, SubscriberBase, RequestorBase,
    DEFAULT_PORTS, MessageType, safe_execute, load_config
)
from .state import UIState, SystemMode, global_state

# Setup logger with proper path handling
logger = setup_logger("ui")

# Ensure log directory exists and add file handler
script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log_dir = os.path.join(script_dir, "logs")

os.makedirs(log_dir, exist_ok=True)
file_handler = logging.FileHandler(os.path.join(log_dir, "ui.log"))
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.info(f"UI logger initialized. Logging to: {os.path.join(log_dir, 'ui.log')}")

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
        
        # Calculate dimensions for animation panel - much smaller circle
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
            
        # Pre-render animation frames using pygame.Surface for better performance
        self.animation_frames = self._create_animation_frames(RED, 10)
    
    def _fallback_font_init(self):
        """Initialize fallback fonts if system fonts are unavailable."""
        # Use PyGame's built-in fonts as fallback
        self.title_font = pygame.font.SysFont("sans", self.title_font_size)
        self.text_font = pygame.font.SysFont("sans", self.text_font_size)
        self.small_font = pygame.font.SysFont("monospace", self.small_font_size)
    
    def _create_animation_frames(self, color, num_frames):
        """
        Pre-render animation frames using surfaces with pre-drawn circles.
        
        This method creates and caches all animation frames in memory,
        which is much more efficient than redrawing vectors every frame.
        """
        frames = []
        animation_size = self.animation_size
        
        # Try to import pygame.gfxdraw for better circle rendering if available
        try:
            import pygame.gfxdraw
            use_gfxdraw = True
        except ImportError:
            use_gfxdraw = False
        
        for i in range(num_frames):
            # Calculate even more subtle pulse factor (0.92 to 1.0 for very subtle animation)
            pulse_factor = 0.92 + 0.08 * abs(num_frames/2 - i) / (num_frames/2)
            
            # Create surface for this frame with solid background and pixel alpha
            surface = pygame.Surface((animation_size, animation_size), flags=SRCALPHA)
            surface.fill((0, 0, 0, 0))  # Transparent background
            
            # Calculate circle parameters
            radius = int(animation_size // 2.5 * pulse_factor)
            center_x = animation_size // 2
            center_y = animation_size // 2
            
            # Draw filled circle using the most efficient method available
            if use_gfxdraw:
                # Use gfxdraw for smoother circles
                pygame.gfxdraw.filled_circle(
                    surface, center_x, center_y, radius, color
                )
            else:
                # Fall back to standard pygame drawing
                pygame.draw.circle(surface, color, (center_x, center_y), radius)
            
            # Store the pre-rendered surface
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
        """Initialize the optimized UI node using the exact configured resolution."""
        logger.info("Initializing UI node...")
        
        # Load configuration
        self.config = load_config(config_path) if config_path else {}
        
        # Initialize PyGame with better driver selection
        logger.info("Initializing pygame...")
        os.environ['SDL_VIDEODRIVER'] = 'x11'  # Force X11 driver for better resolution control
        pygame.init()
        
        # Display init with system info
        pygame.display.init()
        info = pygame.display.Info()
        logger.info(f"System display capabilities: {info.current_w}x{info.current_h}")
        
        # Use configured exact resolution - no scaling
        self.width = self.config.get("ui", {}).get("width", 800)
        self.height = self.config.get("ui", {}).get("height", 1280)
        self.fps = self.config.get("ui", {}).get("fps", 60)
        self.fullscreen = self.config.get("ui", {}).get("fullscreen", True)
        
        logger.info(f"Enforcing exact display resolution: {self.width}x{self.height}")
        
        # Create window with hardcoded resolution that matches config
        # Use SCALED flag to maintain aspect ratio but enforce resolution
        if self.fullscreen:
            flags = FULLSCREEN | HWSURFACE | DOUBLEBUF | SCALED
            logger.info("Setting fullscreen mode with forced resolution")
            # For fullscreen, we need to set the video mode explicitly
            pygame.display.set_mode((self.width, self.height), flags)
        else:
            flags = HWSURFACE | DOUBLEBUF
            logger.info("Setting windowed mode")
            pygame.display.set_mode((self.width, self.height), flags)
        
        pygame.display.set_caption("Reactive Companion")
        
        # Verify actual screen size after setting mode
        self.screen = pygame.display.get_surface()
        actual_width, actual_height = self.screen.get_size()
        logger.info(f"Actual display size after setup: {actual_width}x{actual_height}")
        
        # If there's a mismatch, try one more time with a different approach
        if actual_width != self.width or actual_height != self.height:
            logger.warning(f"Resolution mismatch! Trying alternate approach...")
            
            # Alternative approach using a specific combination of flags
            if self.fullscreen:
                # Sometimes removing SCALED flag helps with exact resolution
                flags = FULLSCREEN | HWSURFACE | DOUBLEBUF
                self.screen = pygame.display.set_mode((self.width, self.height), flags)
                logger.info("Retrying with different flags combination")
            
            # Check again
            actual_width, actual_height = self.screen.get_size()
            logger.info(f"Revised display size: {actual_width}x{actual_height}")
            
            # Update dimensions based on what we actually got
            self.width = actual_width
            self.height = actual_height
        
        # Create subsurfaces for partial updates
        self.top_panel_height = self.height // 2
        self.top_surface = self.screen.subsurface((0, 0, self.width, self.top_panel_height))
        self.bottom_surface = self.screen.subsurface((0, self.top_panel_height, 
                                                     self.width, self.height - self.top_panel_height))
        
        # Initialize state
        self.state = global_state
        self.state.show_debug = True
        
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
        self.bottom_update_counter = 0
        self.last_frame_time = time.time()
        
        # Create debug metrics dictionary
        self.debug_metrics = {
            "frame_render_times": [],
            "avg_render_time": 0.0,
            "using_gfxdraw": False,
            "animation_cache_size": 0,
            "fullscreen_mode": self.fullscreen,
            "last_blit_time": 0.0,
            "last_surface_time": 0.0,
        }
        
        # Running flag
        self.is_running = False
        logger.info("UI node initialization complete")
    
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
                    logger.info(f"Debug mode toggled: {self.state.show_debug}")
                
                elif event.key == pygame.K_f:
                    # Toggle fullscreen with exact resolution
                    self.fullscreen = not self.fullscreen
                    
                    # Enforce the exact resolution when toggling
                    if self.fullscreen:
                        flags = FULLSCREEN | HWSURFACE | DOUBLEBUF | SCALED
                    else:
                        flags = HWSURFACE | DOUBLEBUF
                    
                    # Set mode with configured resolution
                    self.screen = pygame.display.set_mode((self.width, self.height), flags)
                    logger.info(f"Toggled fullscreen mode to {self.fullscreen}, resolution: {self.width}x{self.height}")
                    
                    # Recreate subsurfaces after display mode change
                    self.top_surface = self.screen.subsurface((0, 0, self.width, self.top_panel_height))
                    self.bottom_surface = self.screen.subsurface((0, self.top_panel_height, 
                                                                self.width, self.height - self.top_panel_height))
                    self.debug_metrics["fullscreen_mode"] = self.fullscreen
    
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
        # Measure rendering time
        start_time = time.perf_counter()
        
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
        try:
            surface_start = time.perf_counter()
            self.top_surface.fill(BLACK, update_rect)
            self.debug_metrics["last_surface_time"] = (time.perf_counter() - surface_start) * 1000
            
            # Blit the pre-rendered animation frame
            blit_start = time.perf_counter()
            self.top_surface.blit(animation_frame, (center_x, center_y))
            self.debug_metrics["last_blit_time"] = (time.perf_counter() - blit_start) * 1000
            
            # Record total rendering time
            frame_time = (time.perf_counter() - start_time) * 1000  # Convert to ms
            self.debug_metrics["frame_render_times"].append(frame_time)
            
            # Keep only the last 10 frame times
            if len(self.debug_metrics["frame_render_times"]) > 10:
                self.debug_metrics["frame_render_times"].pop(0)
            
            # Calculate average render time
            if self.debug_metrics["frame_render_times"]:
                self.debug_metrics["avg_render_time"] = sum(
                    self.debug_metrics["frame_render_times"]
                ) / len(self.debug_metrics["frame_render_times"])
        except Exception as e:
            logger.error(f"Error during rendering top panel: {e}")
    
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
        """Render enhanced debug information in the bottom-right corner."""
        if not self.state.show_debug:
            return
        
        # Basic debug information
        debug_info = [
            f"FPS: {self.state.fps}",
            f"CPU: {self.monitor.cpu_usage:.1f}%",
            f"MEM: {self.monitor.memory_usage:.1f}MB",
            f"TEMP: {self.monitor.temperature:.1f}°C",
            f"Res: {self.width}x{self.height}",
            "",  # Empty line as separator
            f"RENDER: {self.debug_metrics['avg_render_time']:.2f}ms",
            f"BLIT: {self.debug_metrics['last_blit_time']:.2f}ms",
            f"SURFACE: {self.debug_metrics['last_surface_time']:.2f}ms",
            f"CACHE: {self.debug_metrics['animation_cache_size']:.1f}KB",
            f"GFXDRAW: {'Yes' if self.debug_metrics['using_gfxdraw'] else 'No'}",
            f"ANIM: {self.current_frame+1}/{len(self.assets.animation_frames)}",
            f"FULLSCREEN: {'Yes' if self.fullscreen else 'No'}"
        ]
        
        # Calculate dimensions for debug panel - wider to fit more text
        bg_width = 200  # Increased width for more detailed info
        bg_height = (len(debug_info) * (self.assets.small_font_size + 5)) + 10
        
        # Draw solid background (right-aligned but moved left a bit)
        bg_rect = pygame.Rect(
            self.width - bg_width - 20,  # Adjusted padding
            self.height - self.top_panel_height - bg_height - 10,
            bg_width,
            bg_height
        )
        
        # Draw background and border
        pygame.draw.rect(self.bottom_surface, BLACK, bg_rect)
        pygame.draw.rect(self.bottom_surface, GRAY, bg_rect, 1)  # 1px border
        
        # Render each line of debug info
        for i, info in enumerate(debug_info):
            # Use different colors for headers and values
            text_color = WHITE if info == "" or ":" not in info else LIGHT_GRAY
            
            self.assets.render_text(
                self.bottom_surface,
                info,
                "small",
                self.width - bg_width - 15,  # Adjusted padding for text
                self.height - self.top_panel_height - bg_height + (i * (self.assets.small_font_size + 5)) + 5,
                text_color
            )


def main() -> None:
    """Main entry point for the UI node."""
    try:
        # Print Python version and module paths for debugging
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Pygame version: {pygame.version.ver}")
        
        parser = argparse.ArgumentParser(description="UI Node")
        parser.add_argument("--config", type=str, help="Path to configuration file")
        args = parser.parse_args()
        
        # Create and start the UI node
        node = UINode(args.config)
        node.start()
    except Exception as e:
        logger.error(f"Error starting UI: {e}", exc_info=True)
        print(f"ERROR: Failed to start UI: {e}")
        
        # Print traceback for better debugging
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
