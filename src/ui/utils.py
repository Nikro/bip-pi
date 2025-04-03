"""
Utility functions and constants for the UI module.
Contains shared functionality used by multiple UI components.
"""

import os
import logging
from typing import Tuple

# Define colors - in normalized OpenGL format (0.0-1.0)
BLACK = (0.0, 0.0, 0.0, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)
GRAY = (0.5, 0.5, 0.5, 1.0)
LIGHT_GRAY = (0.8, 0.8, 0.8, 1.0)
RED = (1.0, 0.0, 0.0, 1.0)

# Font paths - using system fonts for better compatibility
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
MONO_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

# Configure logger for the UI module
def setup_ui_logger() -> logging.Logger:
    """
    Configure and return the UI module logger with appropriate handlers.
    
    Returns:
        Logger object configured for UI module
    """
    from ..common import setup_logger
    
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
    
    return logger

# Create logger instance
logger = setup_ui_logger()

def configure_gl_environment() -> None:
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

def get_system_temperature() -> float:
    """
    Get the current system temperature.
    
    Returns:
        System temperature in Celsius or 0.0 if unavailable
    """
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
