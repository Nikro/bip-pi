"""
Tests for the brains node.

This module contains unit tests for the brains node and its components.
"""

import unittest
import json
import os
from unittest.mock import patch, MagicMock

from src.brains.langchain_agent import LangChainAgent
from src.brains.brains import BrainsNode


class TestLangChainAgent(unittest.TestCase):
    """Tests for the LangChainAgent class."""
    
    def test_initialization(self):
        """Test initialization of the LangChainAgent."""
        config = {
            "model": "test_model",
            "temperature": 0.5
        }
        agent = LangChainAgent(config)
        
        # Check initialization
        self.assertEqual(agent.config, config)
    
    def test_process(self):
        """Test the process method with stub implementation."""
        agent = LangChainAgent({})
        
        # Call process with a test message
        result = agent.process("Hello, world!")
        
        # Check that we got a response
        self.assertIn("response", result)
        self.assertIn("Hello, world!", result["response"])
        self.assertIn("confidence", result)
        self.assertIn("processing_time", result)
    
    def test_text_to_speech(self):
        """Test the text_to_speech stub method."""
        agent = LangChainAgent({})
        
        # Call the stub method
        result = agent.text_to_speech("Hello")
        
        # With stub implementation, this should return None
        self.assertIsNone(result)
    
    def test_speech_to_text(self):
        """Test the speech_to_text stub method."""
        agent = LangChainAgent({})
        
        # Call the stub method with dummy data
        text, confidence = agent.speech_to_text(b"dummy audio data")
        
        # Check we got a response
        self.assertIsInstance(text, str)
        self.assertIsInstance(confidence, float)


class TestBrainsNode(unittest.TestCase):
    """Tests for the BrainsNode class."""
    
    @patch('src.brains.brains.ResponderBase')
    @patch('src.brains.brains.SubscriberBase')
    @patch('src.brains.brains.LangChainAgent')
    def test_initialization(self, mock_agent, mock_subscriber, mock_responder):
        """Test initialization of the BrainsNode."""
        # Setup mocks
        mock_responder.return_value = MagicMock()
        mock_subscriber.return_value = MagicMock()
        mock_agent.return_value = MagicMock()
        
        # Create node
        node = BrainsNode()
        
        # Check initialization
        self.assertFalse(node.is_running)
        self.assertIsNotNone(node.config)
        self.assertIsNotNone(node.responder)
        self.assertIsNotNone(node.subscriber)
        self.assertIsNotNone(node.agent)
        self.assertIsNone(node.background_thread)
    
    @patch('src.brains.brains.ResponderBase')
    @patch('src.brains.brains.SubscriberBase')
    @patch('src.brains.brains.LangChainAgent')
    def test_handle_request(self, mock_agent, mock_subscriber, mock_responder):
        """Test handling requests."""
        # Setup mocks
        mock_responder.return_value = MagicMock()
        mock_subscriber.return_value = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent.return_value = mock_agent_instance
        
        # Configure mock agent
        mock_agent_instance.speech_to_text.return_value = ("test transcription", 0.9)
        mock_agent_instance.text_to_speech.return_value = b"audio data"
        
        # Create node
        node = BrainsNode()
        
        # Test handling STT request
        stt_request = {
            "type": "stt_request",
            "payload": {"audio_data": b"test audio data"}
        }
        result = node._handle_request(stt_request)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["text"], "test transcription")
        self.assertEqual(result["confidence"], 0.9)
        
        # Test handling TTS request
        tts_request = {
            "type": "tts_request",
            "payload": {"text": "test text"}
        }
        result = node._handle_request(tts_request)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["audio_data"], b"audio data")
        
        # Test handling unknown request
        unknown_request = {
            "type": "unknown",
            "payload": {}
        }
        result = node._handle_request(unknown_request)
        self.assertEqual(result["status"], "error")
    
    @patch('src.brains.brains.ResponderBase')
    @patch('src.brains.brains.SubscriberBase')
    @patch('src.brains.brains.LangChainAgent')
    def test_handle_trigger(self, mock_agent, mock_subscriber, mock_responder):
        """Test handling trigger events."""
        # Setup mocks
        mock_responder.return_value = MagicMock()
        mock_subscriber.return_value = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent.return_value = mock_agent_instance
        
        # Configure mock agent
        mock_agent_instance.process.return_value = {
            "response": "Test response",
            "confidence": 0.9,
            "processing_time": 0.1
        }
        
        # Create node
        node = BrainsNode()
        
        # Test handling audio trigger with text
        audio_trigger = {
            "trigger_type": "audio",
            "data": {"text": "Hello"},
            "source": "awareness"
        }
        node._handle_trigger(audio_trigger)
        mock_agent_instance.process.assert_called_once_with("Hello")
        
        # Test handling audio trigger without text
        mock_agent_instance.process.reset_mock()
        empty_trigger = {
            "trigger_type": "audio",
            "data": {},
            "source": "awareness"
        }
        node._handle_trigger(empty_trigger)
        mock_agent_instance.process.assert_not_called()


if __name__ == '__main__':
    unittest.main()
