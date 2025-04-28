"""
Asset management for the UI module.
Handles loading and managing fonts, textures, and other UI resources.
"""

import math
from typing import Dict, Tuple, List

import pygame

from .utils import FONT_PATH, MONO_FONT_PATH, logger
from .gl_components import GLText, Circle


class UIAssets:
    """Container for OpenGL-based UI assets with proper hardware acceleration."""

    def __init__(self, screen_width: int, screen_height: int):
        """
        Initialize and pre-render UI assets once to avoid runtime overhead.

        Args:
            screen_width: Width of the screen in pixels
            screen_height: Height of the screen in pixels
        """
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

        # Animation configuration - MODIFIED for slower, smoother pulse
        # Create a 10-second full cycle animation (5s growing, 5s shrinking)
        # Assuming 50fps: 10 seconds * 50 frames/second = 500 frames
        self.animation_frames = 500
        self.pulse_factors = self._calculate_pulse_factors()

    def _calculate_pulse_factors(self) -> List[float]:
        """
        Pre-calculate animation pulse factors for efficiency.
        Creates a smoother, slower sine-wave based pulse animation.

        Returns:
            List of pulse factors for each animation frame
        """
        factors = []
        for i in range(self.animation_frames):
            # Use sine wave for smooth transitions (0 to 2π range)
            # Scale to provide 25% size variation (0.8 to 1.2)
            phase = (i / self.animation_frames) * 2 * math.pi

            # Slower, gentler pulse with less extreme size changes
            pulse_factor = 1.0 + 0.2 * math.sin(phase)
            factors.append(pulse_factor)
        return factors

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
