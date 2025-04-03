"""
OpenGL-based rendering components for UI rendering.
Optimized for Mali400/Lima GPU on low-powered ARM devices.
"""

import math
from typing import Dict, Tuple, Optional

# Import OpenGL libraries - needed for component classes
import pygame
from OpenGL.GL import *

from .utils import logger


class GLTexture:
    """
    OpenGL texture wrapper for efficient hardware-accelerated rendering.
    Optimized for Mali400/Lima GPU with direct texture creation from PyGame surfaces.
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
        
        # Use power of two textures for better performance on Mali400
        self.tex_width = self._next_power_of_two(self.width)
        self.tex_height = self._next_power_of_two(self.height)
        
        # Generate texture ID
        self.texture_id = glGenTextures(1)
        
        # Bind and configure the texture
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        
        # Set texture parameters - LINEAR is best on Mali400 for text rendering
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        
        # Set texture wrapping mode
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        
        # Determine format based on whether alpha is needed
        self.internal_format = GL_RGBA if is_alpha else GL_RGB
        self.format = GL_RGBA if is_alpha else GL_RGB
        
        # Allocate empty texture memory with power-of-two dimensions
        glTexImage2D(
            GL_TEXTURE_2D, 0, self.internal_format,
            self.tex_width, self.tex_height, 0,
            self.format, GL_UNSIGNED_BYTE, None
        )
    
    def _next_power_of_two(self, value: int) -> int:
        """
        Find the next power of two greater than or equal to the value.
        Mali400 performs best with power-of-two textures.
        
        Args:
            value: Input value
            
        Returns:
            Next power of two
        """
        # Quick optimization for powers of two
        if value & (value - 1) == 0:
            return value
            
        # Find next power of two
        power = 1
        while power < value:
            power *= 2
        return power
    
    def update_from_surface(self, surface: pygame.Surface):
        """
        Update texture content efficiently from a PyGame surface.
        
        Args:
            surface: PyGame surface to upload to texture
        """
        # Convert surface to the right format for direct upload
        if self.is_alpha:
            tex_surface = surface.convert_alpha()
        else:
            tex_surface = surface.convert()
        
        # Pre-scale if needed to power-of-two dimensions 
        if tex_surface.get_width() != self.tex_width or tex_surface.get_height() != self.tex_height:
            if tex_surface.get_width() > self.tex_width or tex_surface.get_height() > self.tex_height:
                # Create a larger texture if needed
                self.tex_width = self._next_power_of_two(max(self.tex_width, tex_surface.get_width()))
                self.tex_height = self._next_power_of_two(max(self.tex_height, tex_surface.get_height()))
                
                # Recreate texture with new dimensions
                glBindTexture(GL_TEXTURE_2D, self.texture_id)
                glTexImage2D(
                    GL_TEXTURE_2D, 0, self.internal_format,
                    self.tex_width, self.tex_height, 0, 
                    self.format, GL_UNSIGNED_BYTE, None
                )
        
        # Get raw pixel data - using GL_UNSIGNED_BYTE for maximum compatibility
        tex_data = pygame.image.tostring(tex_surface, "RGBA" if self.is_alpha else "RGB", True)
        
        # Update texture data efficiently
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        glTexSubImage2D(
            GL_TEXTURE_2D, 0, 0, 0,
            tex_surface.get_width(), tex_surface.get_height(),
            self.format, GL_UNSIGNED_BYTE, tex_data
        )
        
        # Store actual content dimensions
        self.width = tex_surface.get_width()
        self.height = tex_surface.get_height()
    
    def render(self, x: float, y: float, width: float = None, height: float = None):
        """
        Render the texture at the specified screen coordinates.
        
        Args:
            x: X coordinate (top-left)
            y: Y coordinate (top-left)
            width: Width to render (defaults to texture width if None)
            height: Height to render (defaults to texture height if None)
        """
        # Use texture dimensions if no size specified
        if width is None:
            width = self.width
        if height is None:
            height = self.height
        
        # Calculate texture coordinates based on actual content vs. power-of-two size
        tex_right = float(self.width) / float(self.tex_width)
        tex_bottom = float(self.height) / float(self.tex_height)
        
        # Enable texturing and blending with a single state change per texture
        glEnable(GL_TEXTURE_2D)
        if self.is_alpha:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # Bind the texture once
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        
        # Render a textured quad
        glBegin(GL_QUADS)
        
        # Set white color to preserve texture colors
        glColor4f(1.0, 1.0, 1.0, 1.0)
        
        # Top-left
        glTexCoord2f(0.0, 0.0)
        glVertex2f(x, y)
        
        # Top-right
        glTexCoord2f(tex_right, 0.0)
        glVertex2f(x + width, y)
        
        # Bottom-right
        glTexCoord2f(tex_right, tex_bottom)
        glVertex2f(x + width, y + height)
        
        # Bottom-left
        glTexCoord2f(0.0, tex_bottom)
        glVertex2f(x, y + height)
        
        glEnd()
        
        # Disable states
        glDisable(GL_TEXTURE_2D)
        if self.is_alpha:
            glDisable(GL_BLEND)
    
    def cleanup(self):
        """Delete the texture to free GPU memory."""
        try:
            glDeleteTextures([self.texture_id])
        except:
            pass # Handle cleanup errors silently


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


class Circle:
    """
    OpenGL-based circle renderer optimized for Mali400/Lima GPU.
    Uses vertex array for efficient rendering with single draw call.
    """
    def __init__(self, segments: int = 32):
        """
        Initialize the circle renderer with pre-calculated vertices.
        
        Args:
            segments: Number of segments to use for the circle (higher for smoother circles)
        """
        self.segments = segments
        
        # Generate vertices for a unit circle (will be scaled at render time)
        self.vertices = []
        
        # Add center point (first vertex)
        self.vertices.append((0.0, 0.0))
        
        # Pre-calculate all perimeter vertices once
        for i in range(segments + 1):
            angle = 2.0 * math.pi * i / segments
            x = math.cos(angle)
            y = math.sin(angle)
            self.vertices.append((x, y))
    
    def render(self, x: float, y: float, radius: float, color: Tuple[float, float, float, float]):
        """
        Render a filled circle with a single draw call for optimal Mali400/Lima performance.
        
        Args:
            x: X coordinate of center
            y: Y coordinate of center
            radius: Radius of circle
            color: RGBA color tuple (normalized 0.0-1.0)
        """
        # Enable blending for smooth edges and anti-aliasing
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # Set color for the entire primitive
        glColor4f(*color)
        
        # Use triangle fan for most efficient circle rendering
        # Mali400 GPU performs better with a single draw call than multiple primitives
        glBegin(GL_TRIANGLE_FAN)
        
        # Draw all pre-calculated vertices in one batch
        for vx, vy in self.vertices:
            glVertex2f(x + vx * radius, y + vy * radius)
        
        glEnd()
        
        # Disable blending
        glDisable(GL_BLEND)


def draw_line(x1: float, y1: float, x2: float, y2: float, color: Tuple[float, float, float, float]):
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


def draw_rectangle(x: float, y: float, width: float, height: float, color: Tuple[float, float, float, float]):
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


def draw_rectangle_outline(x: float, y: float, width: float, height: float, color: Tuple[float, float, float, float]):
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
