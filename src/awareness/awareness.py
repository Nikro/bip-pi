"""
Awareness node for the reactive companion system.

This node continuously monitors the environment through audio and other 
sensors for triggers that should initiate actions or responses.
"""

import argparse
import time
import threading
from typing import Dict, Any, Optional, List
import os
from pathlib import Path

from ..common import (
    setup_logger, PublisherBase, DEFAULT_PORTS, MessageType, 
    TimedTask, safe_execute
)
from .config import AwarenessConfig
from .audio_monitoring import AudioMonitor

# Setup logger
logger = setup_logger("awareness")


class AwarenessNode:
    """
    Main awareness node class.
    
    This node monitors the environment and publishes trigger events.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the awareness node.
        
        Args:
            config_path: Path to the configuration file
        """
        # Load configuration
        self.config = AwarenessConfig(config_path)
        
        # Setup publisher
        self.publisher = PublisherBase(DEFAULT_PORTS["awareness_pub"])
        logger.info(f"Publisher initialized on port {DEFAULT_PORTS['awareness_pub']}")
        
        # Initialize audio monitor
        models_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "../../models"
        models_dir.mkdir(exist_ok=True, parents=True)
        
        recordings_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "../../recordings"
        recordings_dir.mkdir(exist_ok=True, parents=True)
        
        self.audio_monitor = AudioMonitor(
            output_dir=str(recordings_dir),
            model_path=str(models_dir / "tiny.en")
        )
        
        # Configure audio monitor from awareness config
        self.audio_monitor.sample_rate = self.config.sample_rate
        self.audio_monitor.threshold = self.config.get("audio", "threshold", 0.02)
        self.audio_monitor.min_record_time = self.config.get("audio", "record_seconds", 10)
        self.audio_monitor.silence_limit = self.config.get("audio", "silence_limit", 2.0)
        
        # Subscribe to audio monitor events
        self.audio_monitor.on_recording_complete = self._on_audio_recording_complete
        
        # Keep track of detected triggers
        self.last_trigger_time = 0
        self.is_running = False
    
    def _on_audio_recording_complete(self, recording_path: Path, transcript: Optional[str]) -> None:
        """
        Handle completed audio recordings and transcriptions.
        
        Args:
            recording_path: Path to the recorded audio file
            transcript: Transcribed text (if available)
        """
        # Create data payload for the trigger with enhanced information
        data = {
            "recording_path": str(recording_path),
            "duration": self.audio_monitor.last_recording_duration,
            "transcript": transcript or "",
            "timestamp": time.time()
        }
        
        # Add transcript file path if available
        transcript_path = recording_path.with_suffix('.txt')
        if transcript_path.exists():
            data["transcript_path"] = str(transcript_path)
        
        # Publish trigger event
        self.publish_trigger("audio", data)
        
        # Log the event
        logger.info(f"Audio recording completed: {recording_path}")
        if transcript:
            # Log first 100 characters of transcript for brevity in logs
            logger.info(f"Transcript: {transcript[:100]}{'...' if len(transcript) > 100 else ''}")
    
    def start(self) -> None:
        """Start the awareness node."""
        if self.is_running:
            logger.warning("Awareness node is already running")
            return
            
        self.is_running = True
        
        # Start audio monitoring if enabled
        if self.config.audio_enabled:
            logger.info("Starting audio monitoring")
            # Start in a separate thread to not block the main thread
            threading.Thread(
                target=self.audio_monitor.start_monitoring,
                kwargs={"device": None, "duration": None},
                daemon=True
            ).start()
        
        logger.info("Awareness node started")
        
        # Main loop
        try:
            while self.is_running:
                # Process other sensors or tasks here
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            self.stop()
        except Exception as e:
            logger.error(f"Error in awareness node main loop: {str(e)}")
            self.stop()
    
    def stop(self) -> None:
        """Stop the awareness node."""
        self.is_running = False
        
        # Stop audio monitoring
        self.audio_monitor.stop_monitoring()
        
        logger.info("Awareness node stopped")
    
    def publish_trigger(self, trigger_type: str, data: Dict[str, Any]) -> None:
        """
        Publish a trigger event.
        
        Args:
            trigger_type: Type of trigger (e.g., "audio", "motion")
            data: Additional data about the trigger
        """
        # Prevent trigger spamming with a cooldown period
        current_time = time.time()
        if current_time - self.last_trigger_time < self.config.trigger_cooldown:
            return
            
        self.last_trigger_time = current_time
        
        # Create the payload
        payload = {
            "trigger_type": trigger_type,
            "data": data,
            "source": "awareness"
        }
        
        # Publish the message
        self.publisher.publish(MessageType.TRIGGER_EVENT, payload)
        logger.info(f"Published {trigger_type} trigger event")


def main() -> None:
    """Main entry point for the awareness node."""
    parser = argparse.ArgumentParser(description="Awareness Node")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    args = parser.parse_args()
    
    # Create and start the awareness node
    node = AwarenessNode(args.config)
    node.start()


if __name__ == "__main__":
    main()
