"""
UI node for the reactive companion system.

This module implements the graphical user interface using Pygame,
which visualizes the system state and provides user interaction.
"""

import argparse
import os
import sys
import time
from typing import Dict, Any, List, Tuple, Optional

import pygame
from pygame.locals import *

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
BLUE = (0, 0, 255)
LIGHT_BLUE = (100, 100, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)


class UIAssets:
    """Container for UI assets like fonts and images."""
    
    def __init__(self, screen_width: int, screen_height: int):
        """
        Initialize and load UI assets.
        
        Args:
            screen_width: Width of the display
            screen_height: Height of the display
        """
        # Store screen dimensions for scaling
        self.screen_width = screen_width
        self.screen_height = screen_height
        
        # Calculate dimensions for animation panel
        self.animation_size = min(screen_width, screen_height // 2)
        
        # Ensure pygame font is initialized
        if not pygame.font.get_init():
            pygame.font.init()
        
        # Scale fonts based on screen dimensions
        font_scale = max(1.0, min(screen_width, screen_height) / 480)
        
        # Load fonts
        self.title_font = pygame.font.SysFont("Arial", int(32 * font_scale))
        self.text_font = pygame.font.SysFont("Arial", int(24 * font_scale))
        self.small_font = pygame.font.SysFont("Arial", int(16 * font_scale))
        
        # Load images
        self.images = {}
        try:
            # Add image loading here if needed
            # self.images["logo"] = pygame.image.load("assets/logo.png").convert_alpha()
            pass
        except pygame.error as e:
            logger.error(f"Error loading images: {e}")
        
        # Animation frames for each system mode
        self.animation_frames = {
            SystemMode.IDLE: self._create_animation_frames(BLUE, 10),
            SystemMode.LISTENING: self._create_animation_frames(GREEN, 10),
            SystemMode.PROCESSING: self._create_animation_frames(LIGHT_BLUE, 10),
            SystemMode.RESPONDING: self._create_animation_frames(GREEN, 10),
            SystemMode.ERROR: self._create_animation_frames(RED, 10)
        }
    
    def _create_animation_frames(self, color: Tuple[int, int, int], num_frames: int) -> List[pygame.Surface]:
        """
        Create simple animation frames for a given color.
        
        Args:
            color: RGB color tuple
            num_frames: Number of frames to generate
            
        Returns:
            List of pygame surfaces containing animation frames
        """
        frames = []
        # Make animation size proportional to the screen size
        animation_size = min(self.screen_width, self.screen_height // 2) - 40
        surface_size = (animation_size, animation_size)
        
        # Create a series of pulsing circle frames
        for i in range(num_frames):
            # Calculate pulse factor (0.7 to 1.0) - starting larger for better visibility
            pulse_factor = 0.7 + 0.3 * abs(num_frames/2 - i) / (num_frames/2)
            
            # Create a new transparent surface
            surface = pygame.Surface(surface_size, pygame.SRCALPHA)
            
            # Draw a circle with the pulse factor
            radius = int(animation_size // 2.5 * pulse_factor)
            center = (surface_size[0]//2, surface_size[1]//2)
            
            # Add a subtle glow effect with multiple circles
            for r in range(radius, max(0, radius-20), -2):
                alpha = 255 - (radius - r) * 12
                glow_color = (color[0], color[1], color[2], max(0, min(255, alpha)))
                pygame.draw.circle(surface, glow_color, center, r)
            
            frames.append(surface)
        
        return frames


class UINode:
    """
    Main UI node class.
    
    This node creates a pygame-based GUI to visualize the system state,
    listen for events from other nodes, and allow user interaction.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the UI node.
        
        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        self.config = load_config(config_path) if config_path else {}
        
        # Initialize pygame if not already initialized
        if not pygame.get_init():
            pygame.init()
        
        # Get the display info to handle orientation properly
        display_info = pygame.display.Info()
        
        # Default UI settings
        self.width = self.config.get("ui", {}).get("width", display_info.current_w)
        self.height = self.config.get("ui", {}).get("height", display_info.current_h)
        self.fps = self.config.get("ui", {}).get("fps", 60)  # Higher FPS for smoother animation
        self.fullscreen = self.config.get("ui", {}).get("fullscreen", True)
        
        logger.info(f"Display resolution: {self.width}x{self.height}")
        
        # Initialize state (use the global state singleton)
        self.state = global_state
        # Enable debug mode by default
        self.state.show_debug = True
        
        # Initialize the display with hardware acceleration
        self.display_flags = pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF if self.fullscreen else 0
        self.display = pygame.display.set_mode((self.width, self.height), self.display_flags)
        pygame.display.set_caption("Reactive Companion")
        
        # Create a clock for controlling frame rate
        self.clock = pygame.time.Clock()
        
        # Define the panels (top and bottom)
        self.top_panel_height = self.height // 2
        self.bottom_panel_height = self.height - self.top_panel_height
        
        # Load assets after we know the screen dimensions
        self.assets = UIAssets(self.width, self.height)
        
        # System monitoring
        self.temperature = 0.0
        self.last_temp_check = 0
        
        # Communication
        self.publisher = PublisherBase(DEFAULT_PORTS["ui_pub"])
        self.subscriber = SubscriberBase("localhost", DEFAULT_PORTS["awareness_pub"])
        self.brains_requester = RequestorBase("localhost", DEFAULT_PORTS["brains_rep"])
        
        # Animation state
        self.current_frame = 0
        self.frame_count = 0
        self.last_frame_time = time.time()
        
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
        
        # Clean up pygame
        pygame.quit()
        
        logger.info("UI node stopped")
    
    def _main_loop(self) -> None:
        """Main UI loop that handles events and updates the display."""
        while self.is_running:
            # Process pygame events
            self._process_events()
            
            # Check for messages from other nodes
            self._check_messages()
            
            # Update state (e.g., animations)
            self._update_state()
            
            # Render the UI
            self._render()
            
            # Maintain frame rate
            self.clock.tick(self.fps)
            
            # Update FPS counter
            self.frame_count += 1
            current_time = time.time()
            if current_time - self.last_frame_time >= 1.0:
                self.state.fps = self.frame_count
                self.frame_count = 0
                self.last_frame_time = current_time
    
    def _process_events(self) -> None:
        """Process pygame events."""
        for event in pygame.event.get():
            if event.type == QUIT:
                self.is_running = False
            
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    # Escape key exits
                    self.is_running = False
                
                elif event.key == K_d:
                    # Toggle debug mode
                    self.state.show_debug = not self.state.show_debug
                
                elif event.key == K_f:
                    # Toggle fullscreen
                    self.fullscreen = not self.fullscreen
                    self.display_flags = pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF if self.fullscreen else 0
                    self.display = pygame.display.set_mode(
                        (self.width, self.height), 
                        self.display_flags
                    )
    
    def _check_messages(self) -> None:
        """Check for messages from other nodes."""
        # Non-blocking check for messages with a small timeout
        message = self.subscriber.receive(timeout=10)
        if message:
            # Update state based on the message
            self.state.update_from_message(message)
    
    def _update_state(self) -> None:
        """Update state and animations."""
        # Update animation frame
        if self.frame_count % 2 == 0:  # Update animation faster for smoother visuals
            self.current_frame = (self.current_frame + 1) % 10
            self.state.animation_frame = self.current_frame
            
        # Update system temperature every second
        current_time = time.time()
        if current_time - self.last_temp_check >= 1.0:
            self.temperature = self._get_system_temperature()
            self.last_temp_check = current_time
    
    def _get_system_temperature(self) -> float:
        """
        Get the current system temperature.
        
        Returns:
            Current CPU temperature in Celsius, or 0.0 if unavailable
        """
        try:
            # Try reading from thermal zone 0 (common on Linux systems)
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as temp_file:
                temp = float(temp_file.read().strip()) / 1000.0
                return temp
        except (IOError, ValueError):
            try:
                # Alternative method using vcgencmd (Raspberry Pi specific)
                import subprocess
                result = subprocess.run(
                    ["vcgencmd", "measure_temp"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    # Parse output like "temp=45.8'C"
                    temp_str = result.stdout.strip()
                    temp = float(temp_str.split("=")[1].split("'")[0])
                    return temp
            except (ImportError, subprocess.SubprocessError, ValueError, IndexError):
                pass
                
        return 0.0
    
    def _render(self) -> None:
        """Render the UI based on current state."""
        # Fill the background
        self.display.fill(BLACK)
        
        # Draw the top panel (animation)
        self._render_top_panel()
        
        # Draw the bottom panel (information)
        self._render_bottom_panel()
        
        # Draw debug information if enabled
        if self.state.show_debug:
            self._render_debug()
        
        # Update the display
        pygame.display.flip()
    
    def _render_top_panel(self) -> None:
        """Render the top panel with animation."""
        # Get current mode
        mode = self.state.mode
        
        # Draw a separator line
        pygame.draw.line(
            self.display, 
            GRAY, 
            (0, self.top_panel_height), 
            (self.width, self.top_panel_height),
            3
        )
        
        # Always use red pulsating circle as requested
        animation_frame = self.assets.animation_frames[SystemMode.ERROR][self.current_frame]
        
        # Center the animation in the top panel
        self.display.blit(
            animation_frame, 
            (
                (self.width - animation_frame.get_width()) // 2, 
                (self.top_panel_height - animation_frame.get_height()) // 2
            )
        )
    
    def _render_bottom_panel(self) -> None:
        """Render the bottom panel with information."""
        # Get current mode
        mode = self.state.mode
        
        # Define starting positions
        y_pos = self.top_panel_height + 20
        x_pos = 20
        line_height = self.assets.text_font.get_height() + 10
        
        # Draw mode information
        mode_text = self.assets.title_font.render(f"Mode: {mode.name}", True, WHITE)
        self.display.blit(mode_text, (x_pos, y_pos))
        y_pos += line_height * 1.5
        
        # Draw the last message (if any)
        if self.state.last_message:
            message_text = self.assets.text_font.render(
                f"Message: {self.state.last_message[:30]}...", True, WHITE)
            self.display.blit(message_text, (x_pos, y_pos))
            y_pos += line_height
        
        # Draw the last response (if any)
        if self.state.last_response:
            response_text = self.assets.text_font.render(
                f"Response: {self.state.last_response[:30]}...", True, WHITE)
            self.display.blit(response_text, (x_pos, y_pos))
            y_pos += line_height
        
        # Draw error message if in error state
        if mode == SystemMode.ERROR:
            error_text = self.assets.text_font.render(
                f"Error: {self.state.error_message}", True, RED)
            self.display.blit(error_text, (x_pos, y_pos))
    
    def _render_debug(self) -> None:
        """Render debug information."""
        debug_texts = [
            f"FPS: {self.state.fps}",
            f"CPU: {self.state.cpu_usage:.1f}%",
            f"MEM: {self.state.memory_usage:.1f} MB",
            f"TEMP: {self.temperature:.1f}°C",
            f"Frame: {self.current_frame}/10",
            f"Resolution: {self.width}x{self.height}"
        ]
        
        # Create a semi-transparent background for better readability
        debug_panel = pygame.Surface((220, 30 + len(debug_texts) * 25))
        debug_panel.set_alpha(180)
        debug_panel.fill(BLACK)
        self.display.blit(debug_panel, (self.width - 230, 10))
        
        # Render debug text
        for i, text in enumerate(debug_texts):
            debug_surface = self.assets.small_font.render(text, True, LIGHT_GRAY)
            self.display.blit(debug_surface, (self.width - 220, 20 + i * 25))


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
