"""
UI node for the reactive companion system using hardware-accelerated OpenGL rendering.
Optimized specifically for Mali400/Lima GPU on low-powered ARM devices.
"""

import argparse
import os
import sys
import time
import threading
import math
import logging
from typing import Dict, Any, List, Tuple, Optional, Set

# Import OpenGL libraries first - critical for proper initialization
try:
    import OpenGL
    # Force using EGL/ES2.0 for Mali400 - must be done before any other OpenGL imports
    OpenGL.USE_ACCELERATE = True
    OpenGL.FORWARD_COMPATIBLE_ONLY = True
    from OpenGL.GL import *
    from OpenGL.GLU import *
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False
    print("WARNING: PyOpenGL not available - falling back to software rendering")

# Import PyGame after OpenGL setup
import pygame
from pygame.locals import FULLSCREEN, DOUBLEBUF, OPENGL, SCALED

# Import hardware acceleration specific flags if available
try:
    from pygame.locals import HWACCEL
    HAS_HWACCEL = True
except ImportError:
    HAS_HWACCEL = False
    HWACCEL = 0

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

# Define colors - now in normalized OpenGL format (0.0-1.0)
BLACK = (0.0, 0.0, 0.0, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)
GRAY = (0.5, 0.5, 0.5, 1.0)
LIGHT_GRAY = (0.8, 0.8, 0.8, 1.0)
RED = (1.0, 0.0, 0.0, 1.0)

# Font paths - using system fonts for better compatibility
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
MONO_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


class GLTexture:
    """
    OpenGL texture wrapper for efficient hardware-accelerated rendering.
    Optimized for Mali400/Lima GPU.
    """
    def __init__(self, size: Tuple[int, int], is_alpha: bool = True):
        """
        Initialize an OpenGL texture with the specified size.
        
        Args:
            size: Tuple of (width, height)
            is_alpha: Whether texture supports alpha transparency
        """
        self.width, self.height = size
        self.is_alpha = is_alpha
        
        # Generate texture ID
        self.texture_id = glGenTextures(1)
        
        # Bind and configure the texture
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        
        # Set texture parameters for Mali400/Lima - linear filtering performs well
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        
        # Set texture wrapping mode
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        
        # Determine format based on whether alpha is needed
        self.internal_format = GL_RGBA if is_alpha else GL_RGB
        self.format = GL_RGBA if is_alpha else GL_RGB
        
        # Allocate empty texture memory
        glTexImage2D(
            GL_TEXTURE_2D, 0, self.internal_format,
            self.width, self.height, 0,
            self.format, GL_UNSIGNED_BYTE, None
        )
    
    def update_from_surface(self, surface: pygame.Surface):
        """
        Update the texture content from a PyGame surface.
        
        Args:
            surface: PyGame surface to upload to texture
        """
        # Convert surface to the right format for direct upload
        if self.is_alpha:
            tex_surface = surface.convert_alpha()
        else:
            tex_surface = surface.convert()
        
        # Make sure dimensions match
        if tex_surface.get_width() != self.width or tex_surface.get_height() != self.height:
            tex_surface = pygame.transform.scale(tex_surface, (self.width, self.height))
        
        # Get raw pixel data
        tex_data = pygame.image.tostring(tex_surface, "RGBA" if self.is_alpha else "RGB", True)
        
        # Update texture data
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        glTexSubImage2D(
            GL_TEXTURE_2D, 0, 0, 0,
            self.width, self.height,
            self.format, GL_UNSIGNED_BYTE, tex_data
        )
    
    def render(self, x: float, y: float, width: float, height: float):
        """
        Render the texture at the specified screen coordinates.
        
        Args:
            x: X coordinate (bottom-left)
            y: Y coordinate (bottom-left)
            width: Width to render
            height: Height to render
        """
        # Enable texturing
        glEnable(GL_TEXTURE_2D)
        
        # Enable blending for transparency if needed
        if self.is_alpha:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # Bind the texture
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        
        # Render a textured quad
        glBegin(GL_QUADS)
        
        # Bottom-left
        glTexCoord2f(0.0, 1.0)
        glVertex2f(x, y)
        
        # Bottom-right
        glTexCoord2f(1.0, 1.0)
        glVertex2f(x + width, y)
        
        # Top-right
        glTexCoord2f(1.0, 0.0)
        glVertex2f(x + width, y + height)
        
        # Top-left
        glTexCoord2f(0.0, 0.0)
        glVertex2f(x, y + height)
        
        glEnd()
        
        # Disable texturing and blending
        glDisable(GL_TEXTURE_2D)
        if self.is_alpha:
            glDisable(GL_BLEND)
    
    def cleanup(self):
        """Delete the texture to free GPU memory."""
        glDeleteTextures(1, [self.texture_id])


class GLText:
    """Text rendering manager using OpenGL textures for hardware acceleration."""
    
    def __init__(self, fonts: Dict[str, pygame.font.Font]):
        """
        Initialize the text renderer with prepared fonts.
        
        Args:
            fonts: Dictionary of font objects keyed by name
        """
        self.fonts = fonts
        self.text_cache = {}  # Cache for rendered text textures
    
    def render_text(self, text: str, font_name: str, color: Tuple[float, float, float, float], 
                   x: float, y: float, centered: bool = False) -> Tuple[float, float]:
        """
        Render text with hardware acceleration.
        
        Args:
            text: Text to render
            font_name: Name of font to use ("title", "text", "small")
            color: RGBA color tuple (normalized 0.0-1.0)
            x: X position to render at
            y: Y position to render at
            centered: Whether to center text horizontally
            
        Returns:
            Tuple of (width, height) of rendered text
        """
        if not text:
            return (0, 0)
        
        # Create cache key
        # Convert color to 8-bit for caching (prevent float comparison issues)
        color_8bit = tuple(int(c * 255) for c in color)
        cache_key = (text, font_name, color_8bit)
        
        # Check if text is cached
        if cache_key not in self.text_cache:
            # Pygame uses 8-bit colors - convert from normalized OpenGL
            pygame_color = tuple(int(c * 255) for c in color)
            
            # Render text to surface
            font = self.fonts.get(font_name)
            if not font:
                return (0, 0)
            
            # Render with anti-aliasing
            text_surface = font.render(text, True, pygame_color)
            
            # Get dimensions
            width, height = text_surface.get_size()
            
            # Create a texture for the text
            texture = GLTexture((width, height), True)
            texture.update_from_surface(text_surface)
            
            # Store in cache
            self.text_cache[cache_key] = (texture, width, height)
            
            # Limit cache size
            if len(self.text_cache) > 100:
                # Remove oldest item
                old_key = next(iter(self.text_cache))
                old_texture = self.text_cache[old_key][0]
                old_texture.cleanup()
                del self.text_cache[old_key]
        
        # Get cached texture and dimensions
        texture, width, height = self.text_cache[cache_key]
        
        # Calculate position if centered
        if centered:
            x = x - width / 2
        
        # Render text
        texture.render(x, y, width, height)
        
        return (width, height)
    
    def cleanup(self):
        """Clean up all text textures to free GPU memory."""
        for texture, _, _ in self.text_cache.values():
            texture.cleanup()
        self.text_cache.clear()


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


class Circle:
    """
    OpenGL-based circle renderer optimized for Mali400/Lima GPU.
    Uses vertex buffers and triangle fans for efficient rendering.
    """
    def __init__(self, segments: int = 32):
        """
        Initialize the circle renderer.
        
        Args:
            segments: Number of segments to use for the circle
        """
        self.segments = segments
        
        # Generate vertices for a unit circle (will be scaled at render time)
        self.vertices = []
        self.vertices.append((0.0, 0.0))  # Center point
        
        for i in range(segments + 1):
            angle = 2.0 * math.pi * i / segments
            x = math.cos(angle)
            y = math.sin(angle)
            self.vertices.append((x, y))
    
    def render(self, x: float, y: float, radius: float, color: Tuple[float, float, float, float]):
        """
        Render a filled circle.
        
        Args:
            x: X coordinate of center
            y: Y coordinate of center
            radius: Radius of circle
            color: RGBA color tuple (normalized 0.0-1.0)
        """
        # Enable blending for smooth edges
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # Set color
        glColor4f(*color)
        
        # Draw a triangle fan
        glBegin(GL_TRIANGLE_FAN)
        
        # Add center point
        glVertex2f(x, y)
        
        # Add perimeter points
        for vx, vy in self.vertices:
            glVertex2f(x + vx * radius, y + vy * radius)
        
        glEnd()
        
        # Disable blending
        glDisable(GL_BLEND)


class UIAssets:
    """Container for OpenGL-based UI assets with proper hardware acceleration."""
    
    def __init__(self, screen_width: int, screen_height: int):
        """Initialize and pre-render UI assets once to avoid runtime overhead."""
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        # Calculate dimensions for animation panel
        self.animation_size = min(screen_width, screen_height // 2) // 5
        
        # Pre-calculate font sizes based on screen dimensions
        font_scale = max(0.6, min(screen_width, screen_height) / 640)
        self.title_font_size = int(24 * font_scale)
        self.text_font_size = int(16 * font_scale)
        self.small_font_size = int(10 * font_scale)
        
        # Load fonts
        self._load_fonts()
        
        # Create text renderer
        self.text_renderer = GLText({
            'title': self.title_font,
            'text': self.text_font,
            'small': self.small_font
        })
        
        # Create circle renderer for animation
        self.circle = Circle(segments=64)  # Higher segment count for smoother circles
        
        # Pre-calculate animation parameters
        self.animation_frames = 60
        self.pulse_factors = []
        
        for i in range(self.animation_frames):
            phase = (i / self.animation_frames) * 2 * math.pi
            pulse_factor = 0.85 + 0.15 * ((math.sin(phase) + 1) / 2)
            self.pulse_factors.append(pulse_factor)
    
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
    
    def render_text(self, text: str, font_type: str, x: float, y: float, 
                   color: Tuple[float, float, float, float], centered: bool = False) -> Tuple[float, float]:
        """
        Render text with OpenGL acceleration.
        
        Args:
            text: Text to render
            font_type: Font type ("title", "text", or "small")
            x: X position
            y: Y position
            color: RGBA color tuple (normalized 0.0-1.0)
            centered: Whether to center text horizontally
            
        Returns:
            Tuple of (width, height) of rendered text
        """
        return self.text_renderer.render_text(text, font_type, color, x, y, centered)
    
    def render_circle(self, x: float, y: float, radius: float, color: Tuple[float, float, float, float]):
        """
        Render a circle with OpenGL acceleration.
        
        Args:
            x: X coordinate of center
            y: Y coordinate of center
            radius: Radius of circle
            color: RGBA color tuple (normalized 0.0-1.0)
        """
        self.circle.render(x, y, radius, color)
    
    def cleanup(self):
        """Clean up resources to free GPU memory."""
        self.text_renderer.cleanup()


class UINode:
    """Main UI node class using OpenGL for hardware acceleration."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the UI node with OpenGL hardware acceleration."""
        logger.info("Initializing UI node...")
        
        # Load configuration
        self.config = load_config(config_path) if config_path else {}
        
        # Set up required environment variables before initializing pygame
        self._configure_environment()
        
        # Initialize PyGame and OpenGL
        logger.info("Initializing pygame with OpenGL...")
        pygame.init()
        
        # Display init with system info
        pygame.display.init()
        info = pygame.display.Info()
        logger.info(f"System display capabilities: {info.current_w}x{info.current_h}")
        
        # Use configured resolution
        self.width = self.config.get("ui", {}).get("width", 1050)
        self.height = self.config.get("ui", {}).get("height", 1680)
        self.fps = self.config.get("ui", {}).get("fps", 60)
        self.fullscreen = self.config.get("ui", {}).get("fullscreen", True)
        self.vsync = self.config.get("ui", {}).get("vsync", True)
        
        logger.info(f"Configuring display resolution: {self.width}x{self.height}")
        
        # Create window with OpenGL flags
        self._create_display_surface()
        
        # Check actual window size
        actual_width, actual_height = pygame.display.get_surface().get_size()
        logger.info(f"Actual display size after setup: {actual_width}x{actual_height}")
        
        # Update dimensions if they don't match
        if actual_width != self.width or actual_height != self.height:
            self.width = actual_width
            self.height = actual_height
        
        # Set up OpenGL viewport and projection
        self._configure_opengl()
        
        # Calculate panel heights
        self.top_panel_height = self.height // 2
        
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
        Configure environment variables for optimal OpenGL performance on Mali400/Lima.
        """
        # Set essential PyGame environment variables
        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
        
        # Tell the Mesa driver to use OpenGL ES 2.0 (best supported by Mali400)
        os.environ['MESA_GL_VERSION_OVERRIDE'] = '2.1'
        os.environ['MESA_GLSL_VERSION_OVERRIDE'] = '120'
        
        # Force the Lima driver
        os.environ['GALLIUM_DRIVER'] = 'lima'
        
        # Force using X11 driver for display
        os.environ['SDL_VIDEODRIVER'] = 'x11'
        
        # Disable error checking for better performance
        os.environ['MESA_NO_ERROR'] = '1'
        
        logger.info("Configured environment for OpenGL with Mali400/Lima GPU")
    
    def _create_display_surface(self):
        """Create OpenGL-enabled display surface for hardware acceleration."""
        # Set up proper flags for OpenGL rendering
        flags = OPENGL | DOUBLEBUF
        
        # Add fullscreen if configured
        if self.fullscreen:
            flags |= FULLSCREEN
            logger.info("Fullscreen mode enabled")
        
        # Add scaling if needed (but be cautious, can affect performance)
        if self.config.get("ui", {}).get("allow_scaling", False):
            flags |= SCALED
            logger.info("Display scaling enabled")
        
        # Create the OpenGL-accelerated display
        try:
            logger.info(f"Creating OpenGL display with vsync={self.vsync}")
            self.screen = pygame.display.set_mode(
                (self.width, self.height),
                flags,
                depth=0,  # Let PyGame choose depth best for OpenGL
                vsync=1 if self.vsync else 0
            )
            
            logger.info(f"Display created with OpenGL hardware acceleration")
            
            # Set window caption
            pygame.display.set_caption("Reactive Companion")
        except pygame.error as e:
            logger.error(f"Failed to create OpenGL display: {e}")
            logger.info("Falling back to minimal configuration")
            
            # Try without OpenGL as a fallback
            self.screen = pygame.display.set_mode(
                (self.width, self.height),
                DOUBLEBUF | (FULLSCREEN if self.fullscreen else 0)
            )
    
    def _configure_opengl(self):
        """Configure OpenGL settings for 2D rendering optimized for Mali400/Lima."""
        # Clear color (black background)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        
        # Enable blending for transparency
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # Use a simple 2D orthographic projection
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        
        # Coordinate system: (0,0) at bottom-left, (width,height) at top-right
        glOrtho(0, self.width, 0, self.height, -1, 1)
        
        # Switch to modelview matrix for rendering
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        # Flip the Y-axis to match PyGame conventions (0,0 at top-left)
        glScalef(1.0, -1.0, 1.0)
        glTranslatef(0.0, -self.height, 0.0)
        
        # Report OpenGL information
        logger.info(f"OpenGL Version: {glGetString(GL_VERSION).decode()}")
        logger.info(f"OpenGL Vendor: {glGetString(GL_VENDOR).decode()}")
        logger.info(f"OpenGL Renderer: {glGetString(GL_RENDERER).decode()}")
        logger.info(f"GLSL Version: {glGetString(GL_SHADING_LANGUAGE_VERSION).decode()}")
    
    def _initialize_animation_state(self):
        """Initialize animation state and performance metrics."""
        self.current_frame = 0
        self.frame_count = 0
        self.bottom_update_counter = 0
        self.last_frame_time = time.time()
        self.frame_time_buffer = []
        
        # Create debug metrics dictionary
        self.debug_metrics = {
            "frame_render_times": [],
            "avg_render_time": 0.0,
            "animation_frame": 0,
            "frames_rendered": 0,
            "fullscreen_mode": self.fullscreen,
            "opengl_mode": HAS_OPENGL,
        }
    
    def start(self) -> None:
        """Start the UI node with OpenGL rendering."""
        if self.is_running:
            logger.warning("UI node is already running")
            return
        
        self.is_running = True
        logger.info("UI node started with OpenGL rendering")
        
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
        """Stop the UI node and clean up OpenGL resources."""
        self.is_running = False
        
        # Stop monitoring thread
        if hasattr(self, 'monitor'):
            self.monitor.running = False
        
        # Clean up OpenGL resources
        if hasattr(self, 'assets'):
            self.assets.cleanup()
        
        # Clean up PyGame
        pygame.quit()
        
        logger.info("UI node stopped")
    
    def _main_loop(self) -> None:
        """
        Main rendering loop using OpenGL for hardware acceleration.
        Optimized for Mali400/Lima GPU.
        """
        # Use PyGame's clock for frame timing
        clock = pygame.time.Clock()
        
        # Calculate layout positions
        animation_center_x = self.width // 2
        animation_center_y = self.top_panel_height // 2
        
        # Initial setup
        start_time = time.time()
        
        # Main rendering loop
        while self.is_running:
            # Time tracking for this frame
            frame_start = time.perf_counter()
            
            # Handle events
            self._process_events()
            
            # Check for messages (non-blocking)
            self._check_messages()
            
            # Update animation frame
            self._update_animation()
            
            # Clear the screen
            glClear(GL_COLOR_BUFFER_BIT)
            
            # Reset the modelview matrix
            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
            glScalef(1.0, -1.0, 1.0)
            glTranslatef(0.0, -self.height, 0.0)
            
            # Render the top panel with animation
            self._render_top_panel(animation_center_x, animation_center_y)
            
            # Update bottom panel less frequently (every 10 frames)
            self.bottom_update_counter += 1
            if self.bottom_update_counter >= 10:
                # Render the bottom panel with status info
                self._render_bottom_panel()
                
                # Render debug overlay if enabled
                if self.state.show_debug:
                    self._render_debug_overlay()
                
                self.bottom_update_counter = 0
            
            # Swap buffers to display the rendered frame
            pygame.display.flip()
            
            # Update FPS counter
            self._update_fps_counter(frame_start)
            
            # Increment frame counters
            self.frame_count += 1
            self.debug_metrics["frames_rendered"] = self.frame_count
            
            # Store performance metrics
            frame_time = (time.perf_counter() - frame_start) * 1000  # ms
            self.debug_metrics["frame_render_times"].append(frame_time)
            if len(self.debug_metrics["frame_render_times"]) > 30:
                self.debug_metrics["frame_render_times"].pop(0)
            
            self.debug_metrics["avg_render_time"] = sum(
                self.debug_metrics["frame_render_times"]
            ) / max(len(self.debug_metrics["frame_render_times"]), 1)
            
            # Cap frame rate
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
                    # Toggle fullscreen with proper OpenGL reconfiguration
                    self.fullscreen = not self.fullscreen
                    
                    # Need to recreate the display for fullscreen change
                    flags = OPENGL | DOUBLEBUF
                    if self.fullscreen:
                        flags |= FULLSCREEN
                    
                    # Create new OpenGL surface
                    self.screen = pygame.display.set_mode(
                        (self.width, self.height),
                        flags,
                        vsync=1 if self.vsync else 0
                    )
                    
                    # Reconfigure OpenGL context
                    self._configure_opengl()
                    
                    logger.info(f"Toggled fullscreen mode to {self.fullscreen}")
    
    def _check_messages(self) -> None:
        """Check for messages from other nodes with minimal blocking."""
        message = self.subscriber.receive(timeout=10)
        if message:
            # Update state based on the message
            self.state.update_from_message(message)
    
    def _update_animation(self) -> None:
        """Update animation state."""
        self.current_frame = (self.current_frame + 1) % self.assets.animation_frames
        self.debug_metrics["animation_frame"] = self.current_frame
    
    def _render_top_panel(self, center_x: float, center_y: float) -> None:
        """
        Render the top panel with animated pulsing circle.
        Uses direct OpenGL rendering for efficiency.
        
        Args:
            center_x: X coordinate of panel center
            center_y: Y coordinate of panel center
        """
        # Calculate pulse size based on current frame
        pulse_factor = self.assets.pulse_factors[self.current_frame]
        radius = self.assets.animation_size // 2 * pulse_factor
        
        # Set color with slight transparency
        circle_color = (RED[0], RED[1], RED[2], 0.9)
        
        # Render pulsing circle
        self.assets.render_circle(center_x, center_y, radius, circle_color)
    
    def _render_bottom_panel(self) -> None:
        """
        Render the bottom panel with status information.
        Uses OpenGL-based text rendering.
        """
        # Draw separator line
        self._draw_line(0, self.top_panel_height, self.width, self.top_panel_height, GRAY)
        
        # Render mode text
        mode = self.state.mode
        self.assets.render_text(
            f"Mode: {mode.name}",
            "title",
            20, 
            self.top_panel_height + 20,
            WHITE
        )
        
        # System status information
        y_pos = self.top_panel_height + 20 + self.assets.title_font_size + 10
        status_info = [
            f"System Status: Online",
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
    
    def _render_debug_overlay(self) -> None:
        """
        Render debug information overlay with OpenGL.
        """
        # Prepare debug information
        debug_info = [
            f"FPS: {self.state.fps}",
            f"CPU: {self.monitor.cpu_usage:.1f}%",
            f"MEM: {self.monitor.memory_usage:.1f}MB",
            f"TEMP: {self.monitor.temperature:.1f}°C",
            f"Res: {self.width}x{self.height}",
            "",  # Empty line as separator
            f"RENDER: {self.debug_metrics['avg_render_time']:.2f}ms",
            f"FRAMES: {self.debug_metrics['frames_rendered']}",
            f"ANIM: {self.current_frame+1}/{self.assets.animation_frames}",
            f"GL VER: {glGetString(GL_VERSION).decode()[:10]}",
            f"FULLSCREEN: {'Yes' if self.fullscreen else 'No'}"
        ]
        
        # Calculate background dimensions
        bg_width = 200
        bg_height = (len(debug_info) * (self.assets.small_font_size + 5)) + 10
        
        # Draw semi-transparent background
        self._draw_rectangle(
            self.width - bg_width - 20,
            self.height - bg_height - 10,
            bg_width,
            bg_height,
            (0.0, 0.0, 0.0, 0.7)  # Semi-transparent black
        )
        
        # Draw border
        self._draw_rectangle_outline(
            self.width - bg_width - 20,
            self.height - bg_height - 10,
            bg_width,
            bg_height,
            GRAY
        )
        
        # Render each line of debug info
        y_offset = 10  # Starting Y offset
        for info in debug_info:
            # Use different colors for headers and values
            text_color = WHITE if info == "" or ":" not in info else LIGHT_GRAY
            
            self.assets.render_text(
                info,
                "small",
                self.width - bg_width - 15,
                self.height - bg_height - 5 + y_offset,
                text_color
            )
            
            y_offset += self.assets.small_font_size + 5
    
    def _draw_line(self, x1: float, y1: float, x2: float, y2: float, color: Tuple[float, float, float, float]):
        """
        Draw a line using OpenGL.
        
        Args:
            x1, y1: Start point
            x2, y2: End point
            color: RGBA color tuple (normalized 0.0-1.0)
        """
        glDisable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        glColor4f(*color)
        glBegin(GL_LINES)
        glVertex2f(x1, y1)
        glVertex2f(x2, y2)
        glEnd()
        
        glDisable(GL_BLEND)
    
    def _draw_rectangle(self, x: float, y: float, width: float, height: float, color: Tuple[float, float, float, float]):
        """
        Draw a filled rectangle using OpenGL.
        
        Args:
            x, y: Top-left corner
            width, height: Dimensions
            color: RGBA color tuple (normalized 0.0-1.0)
        """
        glDisable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        glColor4f(*color)
        glBegin(GL_QUADS)
        glVertex2f(x, y)
        glVertex2f(x + width, y)
        glVertex2f(x + width, y + height)
        glVertex2f(x, y + height)
        glEnd()
        
        glDisable(GL_BLEND)
    
    def _draw_rectangle_outline(self, x: float, y: float, width: float, height: float, color: Tuple[float, float, float, float]):
        """
        Draw a rectangle outline using OpenGL.
        
        Args:
            x, y: Top-left corner
            width, height: Dimensions
            color: RGBA color tuple (normalized 0.0-1.0)
        """
        glDisable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        glColor4f(*color)
        glBegin(GL_LINE_LOOP)
        glVertex2f(x, y)
        glVertex2f(x + width, y)
        glVertex2f(x + width, y + height)
        glVertex2f(x, y + height)
        glEnd()
        
        glDisable(GL_BLEND)


def main() -> None:
    """Main entry point for the OpenGL-accelerated UI node."""
    try:
        # Set process priority if possible
        try:
            import os
            os.nice(-10)  # Try to set higher priority
        except (ImportError, OSError):
            pass
        
        # Check that PyOpenGL is available
        if not HAS_OPENGL:
            logger.error("PyOpenGL is required for hardware-accelerated rendering")
            print("ERROR: PyOpenGL not found. Please install with: pip install PyOpenGL PyOpenGL_accelerate")
            sys.exit(1)
        
        # Print diagnostics for debugging
        logger.info(f"Python version: {sys.version}")
        logger.info(f"PyGame version: {pygame.version.ver}")
        logger.info(f"OpenGL available: {HAS_OPENGL}")
        
        parser = argparse.ArgumentParser(description="UI Node with OpenGL Acceleration")
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