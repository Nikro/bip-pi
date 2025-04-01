"""
Configuration for the awareness node.

This module provides configuration options for the awareness node,
including audio monitoring thresholds and other sensor settings.
"""

import json
import os
from typing import Dict, Any, Optional


class AwarenessConfig:
    """Configuration for the awareness node."""
    
    # Default configuration values
    DEFAULT_CONFIG = {
        "audio": {
            "enabled": True,
            "sample_rate": 16000,
            "chunk_size": 1024,
            "amplitude_threshold": 1000,  # Threshold for sound detection
            "record_seconds": 5,          # Seconds to record after trigger
        },
        "video": {
            "enabled": False,
            "resolution": [640, 480],
            "fps": 15,
        },
        "triggers": {
            "cooldown": 2.0,  # Minimum time between triggers in seconds
            "keywords": ["hey", "hello", "computer"],
        },
        "logging": {
            "level": "INFO",
            "file": "awareness.log",
        }
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the configuration from file or defaults.
        
        Args:
            config_path: Path to the configuration file (JSON)
        """
        self.config = self.DEFAULT_CONFIG.copy()
        
        # Try to load configuration from file if provided
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    loaded_config = json.load(f)
                    # Update default config with loaded values (shallow merge)
                    for section, values in loaded_config.items():
                        if section in self.config:
                            self.config[section].update(values)
                        else:
                            self.config[section] = values
            except Exception as e:
                print(f"Error loading configuration from {config_path}: {e}")
    
    def save(self, config_path: str) -> bool:
        """
        Save the current configuration to a file.
        
        Args:
            config_path: Path to save the configuration file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving configuration to {config_path}: {e}")
            return False
    
    @property
    def sample_rate(self) -> int:
        """Get the audio sample rate."""
        return self.config["audio"]["sample_rate"]
    
    @property
    def chunk_size(self) -> int:
        """Get the audio chunk size."""
        return self.config["audio"]["chunk_size"]
    
    @property
    def amplitude_threshold(self) -> int:
        """Get the amplitude threshold for audio triggers."""
        return self.config["audio"]["amplitude_threshold"]
    
    @property
    def record_seconds(self) -> int:
        """Get the number of seconds to record after a trigger."""
        return self.config["audio"]["record_seconds"]
    
    @property
    def trigger_cooldown(self) -> float:
        """Get the minimum time between triggers in seconds."""
        return self.config["triggers"]["cooldown"]
    
    @property
    def keywords(self) -> list:
        """Get the list of trigger keywords."""
        return self.config["triggers"]["keywords"]
    
    @property
    def audio_enabled(self) -> bool:
        """Check if audio monitoring is enabled."""
        return self.config["audio"]["enabled"]
    
    @property
    def video_enabled(self) -> bool:
        """Check if video monitoring is enabled."""
        return self.config["video"]["enabled"]
    
    @property
    def video_resolution(self) -> list:
        """Get video resolution [width, height]."""
        return self.config["video"]["resolution"]
    
    @property
    def video_fps(self) -> int:
        """Get video frames per second."""
        return self.config["video"]["fps"]
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by section and key.
        
        Args:
            section: Configuration section
            key: Configuration key
            default: Default value if not found
            
        Returns:
            Configuration value or default if not found
        """
        return self.config.get(section, {}).get(key, default)
