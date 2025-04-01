"""
Tests for the awareness node.

This module contains unit tests for the awareness node and its components.
"""

import unittest
import json
import os
from unittest.mock import patch, MagicMock

import numpy as np

from src.awareness.config import AwarenessConfig
from src.awareness.awareness import AudioMonitor, AwarenessNode


class TestAwarenessConfig(unittest.TestCase):
    """Tests for the AwarenessConfig class."""
    
    def test_default_config(self):
        """Test that default configuration is loaded correctly."""
        config = AwarenessConfig()
        self.assertEqual(config.sample_rate, 16000)
        self.assertEqual(config.chunk_size, 1024)
        self.assertEqual(config.amplitude_threshold, 1000)
        self.assertEqual(config.trigger_cooldown, 2.0)
        self.assertTrue(config.audio_enabled)
        self.assertFalse(config.video_enabled)
    
    def test_load_config_file(self):
        """Test loading configuration from a file."""
        # Create a temporary config file
        test_config = {
            "audio": {
                "enabled": True,
                "sample_rate": 44100,
                "amplitude_threshold": 2000
            },
            "triggers": {
                "cooldown": 1.0
            }
        }
        
        with open("test_config.json", "w") as f:
            json.dump(test_config, f)
        
        try:
            # Test loading the config
            config = AwarenessConfig("test_config.json")
            
            # Check that values were loaded correctly
            self.assertEqual(config.sample_rate, 44100)
            self.assertEqual(config.amplitude_threshold, 2000)
            self.assertEqual(config.trigger_cooldown, 1.0)
            
            # Default values should still be present for unspecified settings
            self.assertEqual(config.chunk_size, 1024)
        finally:
            # Clean up the temporary file
            os.remove("test_config.json")
    
    def test_save_config(self):
        """Test saving configuration to a file."""
        config = AwarenessConfig()
        
        # Save the config
        result = config.save("test_save_config.json")
        self.assertTrue(result)
        
        try:
            # Check that the file exists and load it back
            self.assertTrue(os.path.exists("test_save_config.json"))
            
            with open("test_save_config.json", "r") as f:
                saved_config = json.load(f)
            
            # Verify some values
            self.assertEqual(saved_config["audio"]["sample_rate"], 16000)
            self.assertEqual(saved_config["triggers"]["cooldown"], 2.0)
        finally:
            # Clean up
            if os.path.exists("test_save_config.json"):
                os.remove("test_save_config.json")


class TestAudioMonitor(unittest.TestCase):
    """Tests for the AudioMonitor class."""
    
    @patch('src.awareness.awareness.pyaudio')
    def test_initialization(self, mock_pyaudio):
        """Test AudioMonitor initialization."""
        # Setup mock
        mock_pyaudio.PyAudio.return_value = MagicMock()
        
        # Create test config
        config = AwarenessConfig()
        
        # Initialize monitor
        monitor = AudioMonitor(config)
        
        # Check initialization
        self.assertFalse(monitor.is_running)
        self.assertIsNone(monitor.thread)
        self.assertIsNone(monitor.stream)
        self.assertIsNotNone(monitor.pa)
    
    @patch('src.awareness.awareness.pyaudio')
    def test_process_audio(self, mock_pyaudio):
        """Test audio processing functionality."""
        # Setup mock
        mock_pyaudio.PyAudio.return_value = MagicMock()
        
        # Create test config with a known threshold
        config = AwarenessConfig()
        
        # Initialize monitor
        monitor = AudioMonitor(config)
        
        # Test with amplitude below threshold
        audio_data = np.zeros(1024, dtype=np.int16)  # All zeros
        result = monitor._process_audio(audio_data)
        self.assertFalse(result)
        
        # Test with amplitude above threshold
        audio_data = np.ones(1024, dtype=np.int16) * 2000  # All 2000
        result = monitor._process_audio(audio_data)
        self.assertTrue(result)


class TestAwarenessNode(unittest.TestCase):
    """Tests for the AwarenessNode class."""
    
    @patch('src.awareness.awareness.PublisherBase')
    def test_initialization(self, mock_publisher):
        """Test AwarenessNode initialization."""
        # Setup mock
        mock_publisher.return_value = MagicMock()
        
        # Create node
        node = AwarenessNode()
        
        # Check initialization
        self.assertFalse(node.is_running)
        self.assertEqual(node.last_trigger_time, 0)
        self.assertIsNotNone(node.config)
        self.assertIsNotNone(node.publisher)
        self.assertIsNotNone(node.audio_monitor)
    
    @patch('src.awareness.awareness.PublisherBase')
    def test_publish_trigger(self, mock_publisher):
        """Test publish_trigger method."""
        # Setup mock
        mock_pub = MagicMock()
        mock_publisher.return_value = mock_pub
        
        # Create node
        node = AwarenessNode()
        
        # Call publish_trigger
        test_data = {"text": "test message"}
        node.publish_trigger("test_trigger", test_data)
        
        # Check that publish was called
        mock_pub.publish.assert_called_once()
        
        # Check cooldown mechanism
        mock_pub.publish.reset_mock()
        node.publish_trigger("second_trigger", {})
        mock_pub.publish.assert_not_called()  # Should be blocked by cooldown


if __name__ == '__main__':
    unittest.main()
