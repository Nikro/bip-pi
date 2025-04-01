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
    
    def __init__(self):
        """Initialize and load UI assets."""
        # Ensure pygame font is initialized
        if not pygame.font.get_init():
            pygame.font.init()
        
        # Load fonts
        self.title_font = pygame.font.SysFont("Arial", 32)
        self.text_font = pygame.font.SysFont("Arial", 24)
        self.small_font = pygame.font.SysFont("Arial", 16)
        
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
        surface_size = (100, 100)
        
        # Create a series of pulsing circle frames
        for i in range(num_frames):
            # Calculate pulse factor (0.5 to 1.0)
            pulse_factor = 0.5 + 0.5 * abs(num_frames/2 - i) / (num_frames/2)
            
            # Create a new transparent surface
            surface = pygame.Surface(surface_size, pygame.SRCALPHA)
            
            # Draw a circle with the pulse factor
            radius = int(40 * pulse_factor)
            pygame.draw.circle(
                surface, 
                color, 
                (surface_size[0]//2, surface_size[1]//2), 
                radius
            )
            
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
        
        # Default UI settings
        self.width = self.config.get("ui", {}).get("width", 800)
        self.height = self.config.get("ui", {}).get("height", 480)
        self.fps = self.config.get("ui", {}).get("fps", 30)
        self.fullscreen = self.config.get("ui", {}).get("fullscreen", True)
        
        # Initialize state (use the global state singleton)
        self.state = global_state
        
        # Initialize pygame if not already initialized
        if not pygame.get_init():
            pygame.init()
        
        # Initialize the display
        self.display_flags = pygame.FULLSCREEN if self.fullscreen else 0
        self.display = pygame.display.set_mode((self.width, self.height), self.display_flags)
        pygame.display.set_caption("Reactive Companion")
        
        # Create a clock for controlling frame rate
        self.clock = pygame.time.Clock()
        
        # Load assets
        self.assets = UIAssets()
        
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
        logger.info("UI node initialized")
    
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
                    self.display_flags = pygame.FULLSCREEN if self.fullscreen else 0
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
        if self.frame_count % 3 == 0:  # Slow down animation
            self.current_frame = (self.current_frame + 1) % 10
            self.state.animation_frame = self.current_frame
        
        # If we're in idle mode for too long, could do something here
        # For example, show different idle animations
    
    def _render(self) -> None:
        """Render the UI based on current state."""
        # Fill the background
        self.display.fill(BLACK)
        
        # Get current mode and render appropriate visuals
        mode = self.state.mode
        
        # Draw the current animation frame for the current mode
        animation_frame = self.assets.animation_frames[mode][self.current_frame]
        self.display.blit(
            animation_frame, 
            ((self.width - animation_frame.get_width()) // 2, 50)
        )
        
        # Draw the mode text
        mode_text = self.assets.title_font.render(f"Mode: {mode.name}", True, WHITE)
        self.display.blit(mode_text, (20, 20))
        
        # Draw the last message (if any)
        if self.state.last_message:
            message_text = self.assets.text_font.render(
                f"Message: {self.state.last_message[:30]}...", True, WHITE)
            self.display.blit(message_text, (20, 200))
        
        # Draw the last response (if any)
        if self.state.last_response:
            response_text = self.assets.text_font.render(
                f"Response: {self.state.last_response[:30]}...", True, WHITE)
            self.display.blit(response_text, (20, 250))
        
        # Draw error message if in error state
        if mode == SystemMode.ERROR:
            error_text = self.assets.text_font.render(
                f"Error: {self.state.error_message}", True, RED)
            self.display.blit(error_text, (20, 300))
        
        # Draw debug information if enabled
        if self.state.show_debug:
            debug_texts = [
                f"FPS: {self.state.fps}",
                f"CPU: {self.state.cpu_usage:.1f}%",
                f"MEM: {self.state.memory_usage:.1f} MB",
                f"Frame: {self.current_frame}/10"
            ]
            
            for i, text in enumerate(debug_texts):
                debug_surface = self.assets.small_font.render(text, True, LIGHT_GRAY)
                self.display.blit(debug_surface, (self.width - 150, 20 + i * 20))
        
        # Update the display
        pygame.display.flip()


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
