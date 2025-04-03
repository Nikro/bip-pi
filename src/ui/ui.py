"""
UI node for the reactive companion system using a lightweight rendering approach.
This implementation focuses on optimized rendering for resource-constrained hardware.
"""

import argparse
import os
import sys
import time
import threading
import math
import logging
from typing import Dict, Any, List, Tuple, Optional, Set

# Simple direct import
import pygame
from pygame.locals import FULLSCREEN, HWSURFACE, DOUBLEBUF, SRCALPHA, SCALED

# Import hardware acceleration specific flags if available
try:
    from pygame.locals import HWACCEL, ASYNCBLIT
    HAS_HWACCEL = True
except ImportError:
    HAS_HWACCEL = False
    HWACCEL, ASYNCBLIT = 0, 0

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

# Import gfxdraw early to ensure it's available
try:
    import pygame.gfxdraw
    HAS_GFXDRAW = True
    logger.info("pygame.gfxdraw module is available for optimized rendering")
except ImportError:
    HAS_GFXDRAW = False
    logger.warning("pygame.gfxdraw module not available - falling back to standard rendering")


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
        
        # Calculate dimensions for animation panel - smaller circle with better proportions
        self.animation_size = min(screen_width, screen_height // 2) // 5
        
        # Pre-calculate font sizes based on screen dimensions
        font_scale = max(0.6, min(screen_width, screen_height) / 640)
        self.title_font_size = int(24 * font_scale)
        self.text_font_size = int(16 * font_scale)
        self.small_font_size = int(10 * font_scale)
        
        # Load and cache fonts
        self._load_fonts()
        
        # Pre-render animation frames for better performance
        self.animation_frames = self._create_animation_frames(RED, 60)
        
        # Cache for text rendering to avoid repeated rendering of the same text
        self.text_cache = {}
    
    def _load_fonts(self):
        """Load system fonts with fallback to built-in fonts if needed."""
        try:
            self.title_font = pygame.font.Font(FONT_PATH, self.title_font_size)
            self.text_font = pygame.font.Font(FONT_PATH, self.text_font_size)
            self.small_font = pygame.font.Font(MONO_FONT_PATH, self.small_font_size)
        except Exception as e:
            logger.error(f"Error loading fonts: {e}")
            self._fallback_font_init()
    
    def _fallback_font_init(self):
        """Initialize fallback fonts if system fonts are unavailable."""
        self.title_font = pygame.font.SysFont("sans", self.title_font_size)
        self.text_font = pygame.font.SysFont("sans", self.text_font_size)
        self.small_font = pygame.font.SysFont("monospace", self.small_font_size)
    
    def _create_animation_frames(self, color, num_frames):
        """
        Pre-render animation frames using surfaces with pre-drawn circles optimized for Mali400/Lima.
        
        Args:
            color: RGB color tuple for the circle
            num_frames: Number of animation frames to generate
            
        Returns:
            List of pre-rendered Surface objects
        """
        frames = []
        animation_size = self.animation_size
        
        # Use power-of-two texture dimensions for better GPU performance
        # Mali GPUs are optimized for power-of-two textures
        pow2_size = 2**math.ceil(math.log2(animation_size))
        
        for i in range(num_frames):
            # Calculate subtle pulse factor - improved smoothness with better range
            phase = (i / num_frames) * 2 * math.pi
            pulse_factor = 0.85 + 0.15 * ((math.sin(phase) + 1) / 2)
            
            # Create hardware-optimized surface
            # Using power-of-two dimensions and 32-bit color for Mali GPUs
            surface = pygame.Surface((pow2_size, pow2_size), flags=SRCALPHA)
            surface.fill((0, 0, 0, 0))  # Transparent background
            
            # Calculate circle parameters
            radius = int(animation_size // 2.5 * pulse_factor)
            center_x = pow2_size // 2
            center_y = pow2_size // 2
            
            # Use the most efficient drawing method available
            if HAS_GFXDRAW:
                # First draw filled circle with solid color
                pygame.gfxdraw.filled_circle(
                    surface, center_x, center_y, radius, color
                )
                # Then add an antialiased edge for smoother appearance
                pygame.gfxdraw.aacircle(
                    surface, center_x, center_y, radius, color
                )
            else:
                # Standard circle drawing as fallback
                pygame.draw.circle(surface, color, (center_x, center_y), radius)
            
            # Convert surface with specific flags for hardware acceleration
            # For Mali400/Lima: 32-bit with alpha optimized for hardware
            hardware_surface = surface.convert_alpha()
            
            # Force upload to texture memory if possible
            # This ensures the texture is already in VRAM, not CPU memory
            if hasattr(hardware_surface, 'get_locked'):
                try:
                    hardware_surface.unlock()
                except:
                    pass
                
            frames.append(hardware_surface)
        
        return frames
    
    def render_text(self, surface, text: str, font_type: str, x: int, y: int, 
                   color) -> pygame.Rect:
        """
        Render text efficiently with caching for repeated text.
        
        Args:
            surface: Surface to render on
            text: Text to render
            font_type: Font type ("title", "text", or "small")
            x: X position
            y: Y position
            color: Text color
            
        Returns:
            Rectangle area that was updated
        """
        # Create a cache key from the text parameters
        cache_key = (text, font_type, color)
        
        # Use cached text surface if available
        if cache_key not in self.text_cache:
            # Select font based on type
            if font_type == "title":
                font = self.title_font
            elif font_type == "text":
                font = self.text_font
            elif font_type == "small":
                font = self.small_font
            else:
                return pygame.Rect(0, 0, 0, 0)
            
            # Pre-render text to a surface (with antialiasing)
            self.text_cache[cache_key] = font.render(text, True, color)
            
            # Limit cache size to prevent memory leaks
            if len(self.text_cache) > 100:
                # Remove a random item if cache gets too large
                self.text_cache.pop(next(iter(self.text_cache)))
        
        # Get the cached surface
        text_surface = self.text_cache[cache_key]
        
        # Blit to destination
        rect = surface.blit(text_surface, (x, y))
        
        return rect


class UINode:
    """Main UI node class with optimizations for low-end hardware."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the optimized UI node using the exact configured resolution."""
        logger.info("Initializing UI node...")
        
        # Load configuration
        self.config = load_config(config_path) if config_path else {}
        
        # Set up required environment variables before initializing pygame
        self._configure_environment()
        
        # Initialize PyGame with better driver selection
        logger.info("Initializing pygame...")
        pygame.init()
        
        # Display init with system info
        pygame.display.init()
        info = pygame.display.Info()
        logger.info(f"System display capabilities: {info.current_w}x{info.current_h}")
        
        # Use configured exact resolution - no scaling
        self.width = self.config.get("ui", {}).get("width", 1050)
        self.height = self.config.get("ui", {}).get("height", 1680)
        self.fps = self.config.get("ui", {}).get("fps", 60)
        self.fullscreen = self.config.get("ui", {}).get("fullscreen", True)
        self.vsync = self.config.get("ui", {}).get("vsync", True)
        self.use_hw_accel = self.config.get("ui", {}).get("use_hardware_acceleration", True)
        
        logger.info(f"Enforcing exact display resolution: {self.width}x{self.height}")
        
        # Create window with optimized flags for performance
        self._create_display_surface()
        
        # Verify actual screen size after setting mode
        self.screen = pygame.display.get_surface()
        actual_width, actual_height = self.screen.get_size()
        logger.info(f"Actual display size after setup: {actual_width}x{actual_height}")
        
        # If there's a mismatch, try fallback approaches
        if actual_width != self.width or actual_height != self.height:
            self._handle_resolution_mismatch(actual_width, actual_height)
        
        # Create subsurfaces for partial updates
        self.top_panel_height = self.height // 2
        self._create_panel_surfaces()
        
        # Initialize state tracking
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
        
        # Animation and performance tracking
        self._initialize_animation_state()
        
        # Running flag
        self.is_running = False
        logger.info("UI node initialization complete")
    
    def _configure_environment(self):
        """
        Configure environment variables for optimal Mali400/Lima performance.
        Uses minimal settings to avoid conflicts while ensuring hardware acceleration.
        """
        # Set essential PyGame environment variables
        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
        os.environ['PYGAME_DETECT_AVX2'] = '1'
        
        # Force using X11 driver which has better compatibility with Lima
        os.environ['SDL_VIDEODRIVER'] = 'x11'
        
        # Force OpenGL renderer with specific optimizations
        os.environ['SDL_RENDER_DRIVER'] = 'opengl'
        os.environ['SDL_HINT_RENDER_DRIVER'] = 'opengl'
        
        # Use nearest neighbor filtering (faster on Mali GPU)
        os.environ['SDL_HINT_RENDER_SCALE_QUALITY'] = '0'
        
        # Enable efficient batch processing of draw calls
        os.environ['SDL_HINT_RENDER_BATCHING'] = '1'
        
        # Disable vertical sync for maximum performance
        os.environ['SDL_HINT_RENDER_VSYNC'] = '0'
        
        # Request direct framebuffer access for better performance
        os.environ['SDL_HINT_FRAMEBUFFER_ACCELERATION'] = '1'
        
        # Log hardware configuration at startup
        logger.info(f"Configuring for Mali400/Lima GPU acceleration")
    
    def _create_display_surface(self):
        """Create optimized display surface with appropriate flags."""
        flags = 0
        
        # Basic flags for performance
        if self.fullscreen:
            flags |= FULLSCREEN
        
        # Add hardware acceleration flags if requested and available
        if self.use_hw_accel:
            flags |= HWSURFACE | DOUBLEBUF
            
            # Add additional acceleration flags if available
            if HAS_HWACCEL:
                flags |= HWACCEL
                if not self.vsync:  # Only use async blit if vsync is disabled
                    flags |= ASYNCBLIT
        
        # Create the display with the configured flags
        if self.vsync:
            # Use vsync to prevent screen tearing
            pygame.display.set_mode((self.width, self.height), flags, vsync=1)
        else:
            pygame.display.set_mode((self.width, self.height), flags)
    
    def _handle_resolution_mismatch(self, actual_width, actual_height):
        """Handle resolution mismatch by trying alternate approaches."""
        logger.warning(f"Resolution mismatch! Trying alternate approach...")
        
        # Try different flag combinations
        for flags_combination in [
            FULLSCREEN | HWSURFACE | DOUBLEBUF,        # Standard fullscreen
            FULLSCREEN | HWSURFACE | DOUBLEBUF | SCALED,  # Try with scaling
            FULLSCREEN                                  # Minimal flags
        ]:
            # Try the new combination
            pygame.display.set_mode((self.width, self.height), flags_combination)
            logger.info(f"Trying with flags: {flags_combination}")
            
            # Check if it worked
            actual_width, actual_height = pygame.display.get_surface().get_size()
            logger.info(f"New display size: {actual_width}x{actual_height}")
            
            # If we got the desired resolution, stop trying
            if actual_width == self.width and actual_height == self.height:
                break
        
        # Update dimensions to actual size
        self.width = actual_width
        self.height = actual_height
    
    def _create_panel_surfaces(self):
        """Create panel surfaces for optimized partial screen updates."""
        self.top_surface = self.screen.subsurface((0, 0, self.width, self.top_panel_height))
        self.bottom_surface = self.screen.subsurface((0, self.top_panel_height, 
                                                     self.width, self.height - self.top_panel_height))
        
        # Create cached background surfaces
        self.top_bg = pygame.Surface((self.width, self.top_panel_height)).convert()
        self.top_bg.fill(BLACK)
        
        self.bottom_bg = pygame.Surface((self.width, self.height - self.top_panel_height)).convert()
        self.bottom_bg.fill(BLACK)
    
    def _initialize_animation_state(self):
        """Initialize animation state and performance metrics."""
        self.current_frame = 0
        self.frame_count = 0
        self.bottom_update_counter = 0
        self.last_frame_time = time.time()
        self.frame_time_buffer = []  # For calculating moving average FPS
        self.last_blit_rects = []    # Track areas for incremental updates
        
        # Create debug metrics dictionary
        self.debug_metrics = {
            "frame_render_times": [],
            "avg_render_time": 0.0,
            "using_gfxdraw": HAS_GFXDRAW,
            "animation_cache_size": 0,
            "fullscreen_mode": self.fullscreen,
            "last_blit_time": 0.0,
            "last_surface_time": 0.0,
            "dirty_rects_count": 0,
        }
        
        # Calculate animation cache size
        bytes_per_pixel = 4  # RGBA
        frame_count = len(self.assets.animation_frames)
        animation_size = self.assets.animation_size
        self.debug_metrics["animation_cache_size"] = (
            (animation_size ** 2) * bytes_per_pixel * frame_count / 1024
        )  # Size in KB
    
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
            import traceback
            traceback.print_exc()
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
        """Optimized main loop using dirty rectangle updates for better performance."""
        # Use pygame's time management for more precise timing
        clock = pygame.time.Clock()
        
        # Track areas that need updating
        dirty_rects = []
        
        # Initial full screen draw
        self.top_surface.blit(self.top_bg, (0, 0))
        self.bottom_surface.blit(self.bottom_bg, (0, 0))
        self._render_top_panel(dirty_rects)
        self._render_bottom_panel(dirty_rects)
        self._render_debug(dirty_rects)
        
        # First frame needs a full update
        pygame.display.flip()
        
        while self.is_running:
            # Time tracking for this frame
            frame_start = time.perf_counter()
            
            # Clear dirty rects for this frame
            dirty_rects.clear()
            
            # Handle events
            self._process_events()
            
            # Check for messages (non-blocking)
            self._check_messages()
            
            # Update animation state
            self._update_animation()
            
            # Render top panel with animation (updates every frame)
            self._render_top_panel(dirty_rects)
            
            # Update bottom panel less frequently (every 10 frames)
            self.bottom_update_counter += 1
            if self.bottom_update_counter >= 10:
                # Render bottom panel
                self._render_bottom_panel(dirty_rects)
                
                # Render debug if enabled
                if self.state.show_debug:
                    self._render_debug(dirty_rects)
                
                self.bottom_update_counter = 0
            
            # Update the display - only update dirty rectangles when possible
            if dirty_rects:
                # Store count for debug
                self.debug_metrics["dirty_rects_count"] = len(dirty_rects)
                
                # Use update for partial screen updates (much faster than flip)
                pygame.display.update(dirty_rects)
            else:
                # Fallback to flip if no dirty rects (rare)
                pygame.display.flip()
            
            # Update FPS counter
            self._update_fps_counter(frame_start)
            
            # Limit frame rate efficiently
            # Sleep just enough to maintain target frame rate
            clock.tick(self.fps)
    
    def _update_fps_counter(self, frame_start):
        """Update FPS counter based on actual frame rendering time."""
        frame_time = time.perf_counter() - frame_start
        
        # Use a buffer for smoother FPS calculation
        self.frame_time_buffer.append(frame_time)
        if len(self.frame_time_buffer) > 30:  # Average over 30 frames
            self.frame_time_buffer.pop(0)
        
        # Calculate average FPS from the buffer
        if self.frame_time_buffer:
            avg_frame_time = sum(self.frame_time_buffer) / len(self.frame_time_buffer)
            if avg_frame_time > 0:
                self.state.fps = int(1.0 / avg_frame_time)
    
    def _process_events(self) -> None:
        """Process PyGame events efficiently."""
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
                    self._create_panel_surfaces()
                    self.debug_metrics["fullscreen_mode"] = self.fullscreen
    
    def _check_messages(self) -> None:
        """Check for messages from other nodes with minimal blocking."""
        message = self.subscriber.receive(timeout=10)
        if message:
            # Update state based on the message
            self.state.update_from_message(message)
    
    def _update_animation(self) -> None:
        """Update animation state."""
        self.current_frame = (self.current_frame + 1) % len(self.assets.animation_frames)
    
    def _render_top_panel(self, dirty_rects: List[pygame.Rect]) -> None:
        """
        Render the top panel with animated content, optimized for Mali400/Lima.
        
        Args:
            dirty_rects: List to which updated areas will be added
        """
        # Measure rendering time
        start_time = time.perf_counter()
        
        # Get current animation frame
        animation_frame = self.assets.animation_frames[self.current_frame]
        
        # Clear only the specific area we're updating to reduce fill operations
        # Mali GPUs are sensitive to large fill operations
        center_x = (self.width - self.assets.animation_size) // 2
        center_y = (self.top_panel_height - self.assets.animation_size) // 2
        
        # Create a rectangle for the area we're updating
        update_rect = pygame.Rect(
            center_x, 
            center_y, 
            animation_frame.get_width(), 
            animation_frame.get_height()
        )
        
        try:
            # Optimized drawing sequence for Mali400/Lima
            
            # 1. Clear only what we need with minimal fill area
            surface_start = time.perf_counter()
            self.top_surface.fill(BLACK, update_rect)
            self.debug_metrics["last_surface_time"] = (time.perf_counter() - surface_start) * 1000
            
            # 2. Efficient blitting - directly copy pre-rendered frame
            blit_start = time.perf_counter()
            self.top_surface.blit(animation_frame, (center_x, center_y))
            self.debug_metrics["last_blit_time"] = (time.perf_counter() - blit_start) * 1000
            
            # 3. Add minimal dirty rectangle - just the animation area
            # Convert to screen coordinates (top panel is a subsurface)
            screen_rect = pygame.Rect(
                update_rect.x,
                update_rect.y,
                update_rect.width,
                update_rect.height
            )
            dirty_rects.append(screen_rect)
            
            # Performance tracking
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
    
    def _render_bottom_panel(self, dirty_rects: List[pygame.Rect]) -> None:
        """
        Render the bottom panel with information.
        
        Args:
            dirty_rects: List to which updated areas will be added
        """
        # Start with a clean bottom panel
        self.bottom_surface.blit(self.bottom_bg, (0, 0))
        
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
        rect = self.assets.render_text(
            self.bottom_surface,
            f"Mode: {mode.name}",
            "title",
            20, 
            20,
            WHITE
        )
        # Add to dirty rects, adjusting for bottom panel position
        dirty_rects.append(pygame.Rect(
            rect.x,
            rect.y + self.top_panel_height,
            rect.width,
            rect.height
        ))
        
        # Render additional status information
        y_pos = 20 + self.assets.title_font_size + 10
        
        # System status
        status_info = [
            f"System Status: Online",
            f"Temperature: {self.monitor.temperature:.1f}°C"
        ]
        
        for info in status_info:
            rect = self.assets.render_text(
                self.bottom_surface,
                info,
                "text",
                20,
                y_pos,
                LIGHT_GRAY
            )
            # Add to dirty rects, adjusting for bottom panel position
            dirty_rects.append(pygame.Rect(
                rect.x,
                rect.y + self.top_panel_height,
                rect.width,
                rect.height
            ))
            y_pos += self.assets.text_font_size + 5
    
    def _render_debug(self, dirty_rects: List[pygame.Rect]) -> None:
        """
        Render enhanced debug information in the bottom-right corner.
        
        Args:
            dirty_rects: List to which updated areas will be added
        """
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
            f"RECTS: {self.debug_metrics['dirty_rects_count']}",
            f"CACHE: {self.debug_metrics['animation_cache_size']:.1f}KB",
            f"GFXDRAW: {'Yes' if self.debug_metrics['using_gfxdraw'] else 'No'}",
            f"ANIM: {self.current_frame+1}/{len(self.assets.animation_frames)}",
            f"FULLSCREEN: {'Yes' if self.fullscreen else 'No'}"
        ]
        
        # Calculate dimensions for debug panel
        bg_width = 200
        bg_height = (len(debug_info) * (self.assets.small_font_size + 5)) + 10
        
        # Draw panel background
        bg_rect = pygame.Rect(
            self.width - bg_width - 20,
            self.height - self.top_panel_height - bg_height - 10,
            bg_width,
            bg_height
        )
        
        # Draw background and border
        pygame.draw.rect(self.bottom_surface, BLACK, bg_rect)
        pygame.draw.rect(self.bottom_surface, GRAY, bg_rect, 1)
        
        # Add entire panel area to dirty rects
        dirty_rects.append(pygame.Rect(
            bg_rect.x,
            bg_rect.y + self.top_panel_height,
            bg_rect.width,
            bg_rect.height
        ))
        
        # Render each line of debug info
        for i, info in enumerate(debug_info):
            # Use different colors for headers and values
            text_color = WHITE if info == "" or ":" not in info else LIGHT_GRAY
            
            self.assets.render_text(
                self.bottom_surface,
                info,
                "small",
                self.width - bg_width - 15,
                self.height - self.top_panel_height - bg_height + (i * (self.assets.small_font_size + 5)) + 5,
                text_color
            )
            # We don't need to add each text line to dirty_rects
            # since we've already added the entire panel area


def main() -> None:
    """Main entry point for the UI node."""
    try:
        # Set process priority if possible
        try:
            import os
            os.nice(-10)  # Try to set higher priority
        except (ImportError, OSError):
            pass
        
        # Print diagnostics for debugging
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
