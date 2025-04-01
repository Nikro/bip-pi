"""
Brains node for the reactive companion system.

This module implements the central processing logic that listens for 
triggers from the awareness node and generates appropriate responses.
"""

import argparse
import json
import os
import threading
import time
from typing import Dict, Any, Optional

from ..common import (
    setup_logger, ResponderBase, SubscriberBase, DEFAULT_PORTS,
    MessageType, TimedTask, safe_execute, load_config
)
from .langchain_agent import LangChainAgent

# Setup logger
logger = setup_logger("brains")


class BrainsNode:
    """
    Main brains node class.
    
    This node listens for triggers and processes them using the LangChain agent.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the brains node.
        
        Args:
            config_path: Path to the configuration file
        """
        # Load configuration
        self.config = load_config(config_path) if config_path else {}
        
        # Setup the responder for direct requests
        self.responder = ResponderBase(DEFAULT_PORTS["brains_rep"])
        logger.info(f"Responder initialized on port {DEFAULT_PORTS['brains_rep']}")
        
        # Setup subscriber to listen for triggers
        self.subscriber = SubscriberBase("localhost", DEFAULT_PORTS["awareness_pub"])
        logger.info(f"Subscriber connected to awareness on port {DEFAULT_PORTS['awareness_pub']}")
        
        # Initialize LangChain agent
        self.agent = LangChainAgent(self.config.get("agent", {}))
        
        # Thread for handling background processing
        self.background_thread: Optional[threading.Thread] = None
        self.is_running = False
    
    def start(self) -> None:
        """Start the brains node."""
        if self.is_running:
            logger.warning("Brains node is already running")
            return
        
        self.is_running = True
        
        # Start background thread for listening to triggers
        self.background_thread = threading.Thread(target=self._background_loop, daemon=True)
        self.background_thread.start()
        
        logger.info("Brains node started")
        
        # Main loop - handle direct requests
        try:
            while self.is_running:
                # Wait for requests with a timeout to allow clean shutdown
                request = self.responder.receive_request(timeout=1000)
                if request:
                    with TimedTask("handle_request", logger=logger):
                        response = self._handle_request(request)
                        self.responder.send_response(MessageType.RESPONSE, response)
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            self.stop()
        except Exception as e:
            logger.error(f"Error in brains node main loop: {str(e)}")
            self.stop()
    
    def stop(self) -> None:
        """Stop the brains node."""
        self.is_running = False
        
        if self.background_thread:
            self.background_thread.join(timeout=2.0)
        
        logger.info("Brains node stopped")
    
    def _background_loop(self) -> None:
        """Background thread for listening to triggers."""
        logger.info("Background processing started")
        
        while self.is_running:
            try:
                # Wait for trigger events with a timeout
                message = self.subscriber.receive(timeout=100)
                
                if message and message.get("type") == MessageType.TRIGGER_EVENT:
                    with TimedTask("process_trigger", logger=logger):
                        self._handle_trigger(message.get("payload", {}))
                        
                # Sleep a tiny bit to prevent CPU hogging
                time.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Error in background loop: {str(e)}")
                time.sleep(0.1)  # Avoid tight loop on errors
    
    def _handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle a direct request to the brains node.
        
        Args:
            request: Request message
            
        Returns:
            Response dictionary
        """
        req_type = request.get("type")
        payload = request.get("payload", {})
        
        response = {
            "status": "error",
            "error": "Unknown request type"
        }
        
        if req_type == MessageType.STT_REQUEST:
            # Speech-to-text request
            audio_data = payload.get("audio_data")
            if audio_data:
                text, confidence = self.agent.speech_to_text(audio_data)
                response = {
                    "status": "success",
                    "text": text,
                    "confidence": confidence
                }
            else:
                response["error"] = "No audio data provided"
                
        elif req_type == MessageType.TTS_REQUEST:
            # Text-to-speech request
            text = payload.get("text")
            if text:
                audio_data = self.agent.text_to_speech(text)
                if audio_data:
                    response = {
                        "status": "success",
                        "audio_data": audio_data
                    }
                else:
                    response["error"] = "Text-to-speech conversion failed"
            else:
                response["error"] = "No text provided"
        
        return response
    
    def _handle_trigger(self, trigger_data: Dict[str, Any]) -> None:
        """
        Handle a trigger event from the awareness node.
        
        Args:
            trigger_data: Trigger event data
        """
        trigger_type = trigger_data.get("trigger_type")
        data = trigger_data.get("data", {})
        
        logger.info(f"Handling trigger: {trigger_type}")
        
        if trigger_type == "audio":
            # Process audio trigger
            text = data.get("text", "")
            if text:
                # Process the text through the agent
                result = self.agent.process(text)
                logger.info(f"Processed text: {text[:50]}...")
                
                # In a real implementation, we might do something with the result,
                # like sending it to a text-to-speech engine or back to the UI
            else:
                logger.warning("Audio trigger received but no text provided")
        
        # Additional trigger types can be handled here
        
        logger.info(f"Trigger {trigger_type} handled")


def main() -> None:
    """Main entry point for the brains node."""
    parser = argparse.ArgumentParser(description="Brains Node")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    args = parser.parse_args()
    
    # Create and start the brains node
    node = BrainsNode(args.config)
    node.start()


if __name__ == "__main__":
    main()
