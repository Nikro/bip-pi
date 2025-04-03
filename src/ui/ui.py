"""
UI node for the reactive companion system using hardware-accelerated OpenGL rendering.
Optimized specifically for Mali400/Lima GPU on low-powered ARM devices.
"""

import argparse
import os
import sys
import time
from typing import Dict, Any, Optional

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

# Import from common framework
from ..common import (
    PublisherBase, SubscriberBase, RequestorBase,
    DEFAULT_PORTS, load_config
)

# Import UI modules
from .state import UIState, SystemMode, global_state
from .utils import logger, configure_gl_environment, WHITE, GRAY, LIGHT_GRAY, RED
from .gl_components import draw_line, draw_rectangle, draw_rectangle_outline
from .ui_assets import UIAssets
from .monitoring import BackgroundMonitor


class UINode:
    """Main UI node class using OpenGL for hardware acceleration."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the UI node with OpenGL hardware acceleration.
        
        Args:
            config_path: Optional path to configuration file
        """
        logger.info("Initializing UI node...")
        
        # Load configuration
        self.config = load_config(config_path) if config_path else {}
        
        # Set up required environment variables before initializing pygame
        configure_gl_environment()
        
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
        
        # FIXED COORDINATE SYSTEM:
        # Coordinate system: (0,0) at top-left, (width,height) at bottom-right
        # This matches PyGame's surface orientation for text rendering
        glOrtho(0, self.width, self.height, 0, -1, 1)
        
        # Switch to modelview matrix for rendering
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
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
        Optimized for Mali400/Lima GPU with continuous rendering for all UI elements.
        """
        # Use PyGame's clock for frame timing
        clock = pygame.time.Clock()
        
        # Calculate layout positions
        animation_center_x = self.width // 2
        animation_center_y = self.top_panel_height // 2
        
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
            
            # Clear the screen with a single call (more efficient)
            glClear(GL_COLOR_BUFFER_BIT)
            
            # Reset the modelview matrix once per frame - FIXED: no flipping needed
            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
            
            # Render both panels every frame to prevent flickering
            self._render_top_panel(animation_center_x, animation_center_y)
            self._render_bottom_panel()
            
            # Render debug overlay if enabled
            if self.state.show_debug:
                self._render_debug_overlay()
            
            # Swap buffers to display the rendered frame
            pygame.display.flip()
            
            # Update FPS counter
            self._update_fps_counter(frame_start)
            
            # Increment frame counter
            self.frame_count += 1
            self.debug_metrics["frames_rendered"] = self.frame_count
            
            # Store performance metrics (keep only the last 10 frames for efficiency)
            frame_time = (time.perf_counter() - frame_start) * 1000  # ms
            self.debug_metrics["frame_render_times"].append(frame_time)
            if len(self.debug_metrics["frame_render_times"]) > 10:
                self.debug_metrics["frame_render_times"].pop(0)
            
            # Calculate average render time
            self.debug_metrics["avg_render_time"] = sum(
                self.debug_metrics["frame_render_times"]
            ) / max(len(self.debug_metrics["frame_render_times"]), 1)
            
            # Cap frame rate
            clock.tick(self.fps)
    
    def _update_fps_counter(self, frame_start: float) -> None:
        """
        Update FPS counter based on actual frame rendering time.
        Modified to provide more accurate FPS measurement for Mali400/Lima GPU.
        
        Args:
            frame_start: Start time of frame rendering in seconds
        """
        frame_time = time.perf_counter() - frame_start
        
        # Use a buffer for smoother FPS calculation
        self.frame_time_buffer.append(frame_time)
        if len(self.frame_time_buffer) > 60:  # Increase sample size for better accuracy
            self.frame_time_buffer.pop(0)
        
        # Calculate average FPS from the buffer
        if self.frame_time_buffer:
            # Calculate real frame rate (not just animation frames)
            avg_frame_time = sum(self.frame_time_buffer) / len(self.frame_time_buffer)
            if avg_frame_time > 0:
                actual_fps = 1.0 / avg_frame_time
                
                # Round to whole number
                self.state.fps = int(round(actual_fps))
                
                # Also store in debug metrics for display
                self.debug_metrics["actual_fps"] = self.state.fps
                
                # Log FPS periodically for monitoring
                if self.frame_count % 300 == 0:  # Log every 300 frames
                    logger.info(f"Current FPS: {self.state.fps} (avg over {len(self.frame_time_buffer)} frames)")
    
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
        draw_line(0, self.top_panel_height, self.width, self.top_panel_height, GRAY)
        
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
        Render debug information overlay with enhanced FPS metrics.
        """
        # Prepare debug information with more detailed performance metrics
        debug_info = [
            f"FPS: {self.state.fps}",  # Actual frames per second
            f"Frame Time: {(sum(self.frame_time_buffer)/max(len(self.frame_time_buffer),1))*1000:.1f}ms",
            f"CPU: {self.monitor.cpu_usage:.1f}%",
            f"MEM: {self.monitor.memory_usage:.1f}MB",
            f"TEMP: {self.monitor.temperature:.1f}°C",
            f"Res: {self.width}x{self.height}",
            "",  # Empty line as separator
            f"RENDER: {self.debug_metrics['avg_render_time']:.2f}ms",
            f"VSYNC: {'On' if self.vsync else 'Off'}",
            f"ANIM: {self.current_frame+1}/{self.assets.animation_frames}",
            f"GL VER: {glGetString(GL_VERSION).decode()[:10]}",
            f"FULLSCREEN: {'Yes' if self.fullscreen else 'No'}"
        ]
        
        # Calculate background dimensions
        bg_width = 200
        bg_height = (len(debug_info) * (self.assets.small_font_size + 5)) + 10
        
        # Draw semi-transparent background
        draw_rectangle(
            self.width - bg_width - 20,
            self.height - bg_height - 10,
            bg_width,
            bg_height,
            (0.0, 0.0, 0.0, 0.7)  # Semi-transparent black
        )
        
        # Draw border
        draw_rectangle_outline(
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