#!/usr/bin/env python3
"""
Demo script for the Reactive Companion System.

This script demonstrates the basic functionality of the reactive companion
system without requiring full hardware setup (audio/video devices).
It simulates the interaction between the three main components:
- Awareness (monitors environment)
- Brains (processes triggers and generates responses)  
- UI (provides visual feedback)
"""

import json
import time
import threading
from typing import Dict, Any
import argparse

# Import system components
from src.common import setup_logger
from src.ui.state import UIState, SystemMode

# Setup logger
logger = setup_logger("demo")


class MockAwarenessNode:
    """Mock awareness node that simulates audio triggers."""
    
    def __init__(self, ui_state: UIState):
        """Initialize with reference to UI state."""
        self.ui_state = ui_state
        self.running = False
        self.demo_phrases = [
            "Hello, how are you today?",
            "What is the weather like?", 
            "Can you help me with something?",
            "Tell me a joke",
            "What time is it?"
        ]
        self.phrase_index = 0
    
    def start_demo(self):
        """Start the demo awareness simulation."""
        self.running = True
        logger.info("Mock Awareness Node started")
        
        while self.running:
            # Wait a bit between triggers
            time.sleep(5)
            
            if not self.running:
                break
                
            # Simulate an audio trigger
            phrase = self.demo_phrases[self.phrase_index]
            self.phrase_index = (self.phrase_index + 1) % len(self.demo_phrases)
            
            logger.info(f"Simulating audio trigger: '{phrase}'")
            
            # Update UI state as if we received a real audio trigger
            trigger_message = {
                "type": "trigger_event", 
                "payload": {
                    "trigger_type": "audio",
                    "data": {
                        "transcript": phrase,
                        "recording_path": f"/tmp/demo_audio_{int(time.time())}.wav",
                        "duration": 2.5
                    }
                }
            }
            
            self.ui_state.update_from_message(trigger_message)
            
            # Simulate processing time
            time.sleep(1)
            self.ui_state.mode = SystemMode.PROCESSING
            
            # Simulate response generation
            time.sleep(2)
            response_message = {
                "type": "response",
                "payload": {
                    "response": f"I heard you say: '{phrase}'. Here's my response!"
                }
            }
            
            self.ui_state.update_from_message(response_message)
            
            # Return to idle after response
            time.sleep(2)
            self.ui_state.mode = SystemMode.IDLE
    
    def stop(self):
        """Stop the demo simulation."""
        self.running = False
        logger.info("Mock Awareness Node stopped")


class DemoTextUI:
    """Simple text-based UI for the demo."""
    
    def __init__(self, ui_state: UIState):
        """Initialize with reference to UI state."""
        self.ui_state = ui_state
        self.running = False
        self.last_mode = None
        self.last_message = ""
        self.last_response = ""
    
    def start_display(self):
        """Start the text UI display loop."""
        self.running = True
        logger.info("Demo Text UI started")
        
        print("\n" + "="*60)
        print("REACTIVE COMPANION SYSTEM - DEMO MODE")
        print("="*60)
        print("Press Ctrl+C to stop the demo")
        print("="*60 + "\n")
        
        while self.running:
            current_state = self.ui_state.to_dict()
            mode = self.ui_state.mode
            message = self.ui_state.last_message
            response = self.ui_state.last_response
            
            # Only update display when something changes
            if (mode != self.last_mode or 
                message != self.last_message or 
                response != self.last_response):
                
                self._update_display(mode, message, response, current_state)
                
                self.last_mode = mode
                self.last_message = message
                self.last_response = response
            
            time.sleep(0.5)
    
    def _update_display(self, mode: SystemMode, message: str, response: str, state: Dict[str, Any]):
        """Update the display with current state."""
        print(f"\n[{time.strftime('%H:%M:%S')}] System Mode: {mode.name}")
        
        if mode == SystemMode.LISTENING and message:
            print(f"🎤 User said: \"{message}\"")
        
        elif mode == SystemMode.PROCESSING:
            print("🧠 Processing input...")
        
        elif mode == SystemMode.RESPONDING and response:
            print(f"🤖 System response: \"{response}\"")
        
        elif mode == SystemMode.IDLE:
            print("😴 System idle - waiting for input...")
        
        # Show transcript history if available
        history = state.get("transcript_history", [])
        if history and len(history) > 1:
            print(f"📝 Recent conversations ({len(history)} total):")
            for i, entry in enumerate(history[:3]):  # Show last 3
                timestamp = time.strftime('%H:%M:%S', time.localtime(entry['timestamp']))
                print(f"   [{timestamp}] \"{entry['text'][:50]}{'...' if len(entry['text']) > 50 else ''}\"")
        
        print("-" * 60)
    
    def stop(self):
        """Stop the text UI."""
        self.running = False
        logger.info("Demo Text UI stopped")


def run_demo(duration_seconds: int = 30):
    """
    Run the reactive companion demo.
    
    Args:
        duration_seconds: How long to run the demo (default: 30 seconds)
    """
    logger.info(f"Starting Reactive Companion Demo (duration: {duration_seconds}s)")
    
    # Create shared UI state
    ui_state = UIState()
    
    # Create demo components
    awareness_mock = MockAwarenessNode(ui_state)
    text_ui = DemoTextUI(ui_state)
    
    # Start components in separate threads
    awareness_thread = threading.Thread(target=awareness_mock.start_demo, daemon=True)
    ui_thread = threading.Thread(target=text_ui.start_display, daemon=True)
    
    try:
        awareness_thread.start()
        ui_thread.start()
        
        # Run for specified duration
        time.sleep(duration_seconds)
        
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    
    finally:
        # Clean shutdown
        logger.info("Stopping demo components...")
        awareness_mock.stop()
        text_ui.stop()
        
        # Wait a bit for threads to stop
        time.sleep(1)
        
        print("\n" + "="*60)
        print("DEMO COMPLETED - Thank you for trying the Reactive Companion!")
        print("="*60)


def main():
    """Main entry point for the demo."""
    parser = argparse.ArgumentParser(description="Reactive Companion System Demo")
    parser.add_argument(
        "--duration", 
        type=int, 
        default=30,
        help="Demo duration in seconds (default: 30)"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        run_demo(args.duration)
    except Exception as e:
        logger.error(f"Demo failed with error: {e}")
        print(f"ERROR: Demo failed - {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())