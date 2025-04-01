"""
Tests for the UI node.

This module contains unit tests for the UI node and its components.
"""

import unittest
from unittest.mock import patch, MagicMock
import time

from src.ui.state import UIState, SystemMode
from src.ui.ui import UINode


class TestUIState(unittest.TestCase):
    """Tests for the UIState class."""
    
    def test_initialization(self):
        """Test UIState initialization with default values."""
        state = UIState()
        self.assertEqual(state.mode, SystemMode.IDLE)
        self.assertEqual(state.last_message, "")
        self.assertEqual(state.last_response, "")
        self.assertEqual(state.error_message, "")
        self.assertEqual(state.animation_frame, 0)
        self.assertEqual(state.brightness, 1.0)
        self.assertFalse(state.show_debug)
        self.assertEqual(state.fps, 0)
        self.assertEqual(state.cpu_usage, 0.0)
        self.assertEqual(state.memory_usage, 0.0)
    
    def test_property_setters(self):
        """Test property setters with state change notifications."""
        state = UIState()
        
        # Mock listener
        mock_listener = MagicMock()
        state.register_listener(mock_listener)
        
        # Set properties and check notifications
        state.mode = SystemMode.LISTENING
        mock_listener.assert_called_with("mode", (SystemMode.IDLE, SystemMode.LISTENING))
        mock_listener.reset_mock()
        
        state.last_message = "Test message"
        mock_listener.assert_called_with("last_message", "Test message")
        mock_listener.reset_mock()
        
        state.last_response = "Test response"
        mock_listener.assert_called_with("last_response", "Test response")
        mock_listener.reset_mock()
        
        state.error_message = "Error occurred"
        mock_listener.assert_called_with("error_message", "Error occurred")
        mock_listener.reset_mock()
        
        state.brightness = 0.5
        mock_listener.assert_called_with("brightness", 0.5)
        mock_listener.reset_mock()
        
        state.show_debug = True
        mock_listener.assert_called_with("show_debug", True)
    
    def test_update_from_message(self):
        """Test updating state from received messages."""
        state = UIState()
        
        # Test trigger event
        trigger_message = {
            "type": "trigger_event",
            "payload": {
                "trigger_type": "audio",
                "data": {"text": "Hello there"}
            }
        }
        state.update_from_message(trigger_message)
        self.assertEqual(state.mode, SystemMode.LISTENING)
        self.assertEqual(state.last_message, "Hello there")
        
        # Test response event
        response_message = {
            "type": "response",
            "payload": {
                "response": "This is a test response"
            }
        }
        state.update_from_message(response_message)
        self.assertEqual(state.mode, SystemMode.RESPONDING)
        self.assertEqual(state.last_response, "This is a test response")
        
        # Test error event
        error_message = {
            "type": "error",
            "payload": {
                "message": "Something went wrong"
            }
        }
        state.update_from_message(error_message)
        self.assertEqual(state.mode, SystemMode.ERROR)
        self.assertEqual(state.error_message, "Something went wrong")
    
    def test_to_dict(self):
        """Test converting state to dictionary."""
        state = UIState()
        state.mode = SystemMode.PROCESSING
        state.last_message = "Test message"
        state.fps = 60
        state.cpu_usage = 25.5
        
        # Get dictionary representation
        state_dict = state.to_dict()
        
        # Check values
        self.assertEqual(state_dict["mode"], "PROCESSING")
        self.assertEqual(state_dict["last_message"], "Test message")
        self.assertEqual(state_dict["fps"], 60)
        self.assertEqual(state_dict["cpu_usage"], 25.5)


@patch('pygame.font.SysFont')
@patch('pygame.display.set_mode')
@patch('pygame.init')
class TestUINode(unittest.TestCase):
    """Tests for the UINode class."""
    
    @patch('src.ui.ui.PublisherBase')
    @patch('src.ui.ui.SubscriberBase')
    @patch('src.ui.ui.RequestorBase')
    def test_initialization(self, mock_requestor, mock_subscriber, mock_publisher, 
                           mock_pygame_init, mock_set_mode, mock_font):
        """Test UINode initialization."""
        # Setup mocks
        mock_publisher.return_value = MagicMock()
        mock_subscriber.return_value = MagicMock()
        mock_requestor.return_value = MagicMock()
        mock_pygame_init.return_value = None
        mock_display = MagicMock()
        mock_set_mode.return_value = mock_display
        mock_font.return_value = MagicMock()
        
        # Create node with test config
        config = {
            "ui": {
                "width": 640,
                "height": 480,
                "fps": 60,
                "fullscreen": False
            }
        }
        
        # Open a file and write the config
        with open("test_ui_config.json", "w") as f:
            json.dump(config, f)
        
        try:
            node = UINode("test_ui_config.json")
            
            # Check initialization
            self.assertEqual(node.width, 640)
            self.assertEqual(node.height, 480)
            self.assertEqual(node.fps, 60)
            self.assertFalse(node.fullscreen)
            self.assertFalse(node.is_running)
            self.assertIsNotNone(node.publisher)
            self.assertIsNotNone(node.subscriber)
            self.assertIsNotNone(node.brains_requester)
        finally:
            # Clean up
            if os.path.exists("test_ui_config.json"):
                os.remove("test_ui_config.json")
    
    @patch('src.ui.ui.PublisherBase')
    @patch('src.ui.ui.SubscriberBase')
    @patch('src.ui.ui.RequestorBase')
    def test_process_events(self, mock_requestor, mock_subscriber, mock_publisher,
                           mock_pygame_init, mock_set_mode, mock_font):
        """Test event processing."""
        # Setup mocks
        mock_publisher.return_value = MagicMock()
        mock_subscriber.return_value = MagicMock()
        mock_requestor.return_value = MagicMock()
        mock_pygame_init.return_value = None
        mock_display = MagicMock()
        mock_set_mode.return_value = mock_display
        mock_font.return_value = MagicMock()
        
        # Create node
        node = UINode()
        
        # We need to patch pygame.event.get to return mock events
        with patch('pygame.event.get') as mock_get_events:
            # Test quit event
            mock_get_events.return_value = [MagicMock(type=pygame.QUIT)]
            node._process_events()
            self.assertFalse(node.is_running)
            
            # Reset running state
            node.is_running = True
            
            # Test escape key
            mock_event = MagicMock(type=pygame.KEYDOWN, key=pygame.K_ESCAPE)
            mock_get_events.return_value = [mock_event]
            node._process_events()
            self.assertFalse(node.is_running)
            
            # Reset running state
            node.is_running = True
            
            # Test debug toggle
            mock_event = MagicMock(type=pygame.KEYDOWN, key=pygame.K_d)
            mock_get_events.return_value = [mock_event]
            self.assertFalse(node.state.show_debug)
            node._process_events()
            self.assertTrue(node.state.show_debug)


if __name__ == '__main__':
    unittest.main()
