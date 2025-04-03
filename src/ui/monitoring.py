"""
Background monitoring for system resources.
Runs in a separate thread to avoid blocking the UI.
"""

import threading
import time
from typing import Optional

from .utils import logger, get_system_temperature


class BackgroundMonitor(threading.Thread):
    """Background thread for system monitoring tasks."""
    
    def __init__(self, ui_node):
        """
        Initialize the background monitor thread.
        
        Args:
            ui_node: Reference to the UI node for updating state
        """
        super().__init__(daemon=True)
        self.ui_node = ui_node
        self.running = True
        self.temperature = 0.0
        self.cpu_usage = 0.0
        self.memory_usage = 0.0
    
    def run(self):
        """Run the monitoring thread."""
        try:
            import psutil
            has_psutil = True
        except ImportError:
            logger.error("psutil not available - system monitoring will be limited")
            has_psutil = False
        
        while self.running:
            # Update system metrics in a separate thread to avoid blocking the UI
            try:
                # Update temperature
                self.temperature = get_system_temperature()
                
                # Update CPU and memory usage if psutil is available
                if has_psutil:
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
