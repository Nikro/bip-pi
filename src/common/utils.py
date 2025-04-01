"""
Utility functions for the reactive companion system.

This module contains various helper functions used across the system.
"""

import logging
import os
import sys
import time
from typing import Any, Dict, Optional

# Configure logging
def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Create a logger with the specified name and level.

    Args:
        name: The name of the logger
        level: The logging level (default: logging.INFO)

    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Create file handler
    file_handler = logging.FileHandler(f"logs/{name}.log")
    file_handler.setFormatter(formatter)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


class TimedTask:
    """Utility class for measuring execution time of tasks."""

    def __init__(self, name: str, logger: Optional[logging.Logger] = None):
        """
        Initialize a timed task.

        Args:
            name: Name of the task for logging
            logger: Logger to use, if None a new one will be created
        """
        self.name = name
        self.logger = logger or setup_logger(f"timed_task_{name}")
        self.start_time = 0

    def __enter__(self) -> 'TimedTask':
        """Start timing when entering context."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Log execution time when exiting context."""
        duration = time.time() - self.start_time
        if exc_type:
            self.logger.error(f"Task '{self.name}' failed after {duration:.4f}s: {exc_val}")
        else:
            self.logger.info(f"Task '{self.name}' completed in {duration:.4f}s")


def safe_execute(func: callable, *args: Any, logger: Optional[logging.Logger] = None, 
                 default_return: Any = None, **kwargs: Any) -> Any:
    """
    Execute a function safely and log any exceptions.

    Args:
        func: Function to execute
        *args: Arguments to pass to the function
        logger: Logger to use, if None a new one will be created
        default_return: Value to return if function fails
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Return value of the function or default_return on failure
    """
    local_logger = logger or setup_logger("safe_execute")
    
    try:
        return func(*args, **kwargs)
    except Exception as e:
        local_logger.error(f"Error executing {func.__name__}: {str(e)}")
        return default_return


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from a JSON file.

    Args:
        config_path: Path to the configuration file

    Returns:
        Dictionary containing the configuration
    """
    import json
    from pathlib import Path
    
    # If config_path is a directory, look for specific defaults
    if config_path and Path(config_path).is_dir():
        module_name = Path(sys.argv[0]).stem
        potential_path = Path(config_path) / f"{module_name}_config.json"
        if potential_path.exists():
            config_path = str(potential_path)
        else:
            # Try generic config.json
            generic_path = Path(config_path) / "config.json"
            if generic_path.exists():
                config_path = str(generic_path)
    
    try:
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                return json.load(f)
        else:
            logger = setup_logger("config_loader")
            logger.warning(f"Config path not found: {config_path}")
            return {}
    except Exception as e:
        logger = setup_logger("config_loader")
        logger.error(f"Failed to load config from {config_path}: {str(e)}")
        return {}


def is_raspberry_pi() -> bool:
    """
    Check if the code is running on a Raspberry Pi.

    Returns:
        True if running on a Raspberry Pi, False otherwise
    """
    try:
        with open('/proc/device-tree/model', 'r') as f:
            return 'Raspberry Pi' in f.read()
    except:
        return False


def is_orange_pi() -> bool:
    """
    Check if the code is running on an Orange Pi.

    Returns:
        True if running on an Orange Pi, False otherwise
    """
    try:
        with open('/proc/device-tree/model', 'r') as f:
            return 'Orange Pi' in f.read()
    except:
        return False


def get_system_info() -> Dict[str, Any]:
    """
    Get system information.

    Returns:
        Dictionary with system information
    """
    import platform
    import psutil
    
    info = {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "cpu_count": psutil.cpu_count(),
        "memory_total": psutil.virtual_memory().total,
    }
    
    # Check for specific SBC type
    if is_raspberry_pi():
        info["sbc_type"] = "Raspberry Pi"
    elif is_orange_pi():
        info["sbc_type"] = "Orange Pi"
    else:
        info["sbc_type"] = "Unknown"
        
    return info
