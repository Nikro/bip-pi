"""
Awareness node for the reactive companion system.

This node continuously monitors the environment through audio and other 
sensors for triggers that should initiate actions or responses.
"""

import argparse
import time
import threading
from typing import Dict, Any, Optional, List
import numpy as np

from ..common import (
    setup_logger, PublisherBase, DEFAULT_PORTS, MessageType, 
    TimedTask, safe_execute
)
from .config import AwarenessConfig

# Setup logger
logger = setup_logger("awareness")


class AudioMonitor:
    """Monitors audio input for trigger events."""
    
    def __init__(self, config: AwarenessConfig):
        """
        Initialize the audio monitor.
        
        Args:
            config: Configuration for the audio monitor
        """
        self.config = config
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        
        # Try to import pyaudio
        try:
            import pyaudio
            self.pa = pyaudio.PyAudio()
            logger.info("PyAudio initialized successfully")
        except ImportError:
            logger.error("PyAudio not found. Audio monitoring will be disabled.")
            self.pa = None
        except Exception as e:
            logger.error(f"Error initializing PyAudio: {str(e)}")
            self.pa = None
            
        # Audio stream
        self.stream = None
    
    def start(self) -> bool:
        """
        Start audio monitoring in a separate thread.
        
        Returns:
            True if started successfully, False otherwise
        """
        if self.is_running:
            logger.warning("Audio monitor is already running")
            return True
            
        if self.pa is None:
            logger.error("PyAudio not initialized. Cannot start audio monitoring.")
            return False
            
        self.is_running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info("Audio monitoring started")
        return True
    
    def stop(self) -> None:
        """Stop audio monitoring."""
        self.is_running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            
        if self.thread:
            self.thread.join(timeout=2.0)
            
        logger.info("Audio monitoring stopped")
    
    def _monitor_loop(self) -> None:
        """Main audio monitoring loop."""
        import pyaudio
        
        # Audio parameters
        format = pyaudio.paInt16
        channels = 1
        rate = self.config.sample_rate
        chunk = self.config.chunk_size
        
        # Open audio stream
        try:
            self.stream = self.pa.open(
                format=format,
                channels=channels,
                rate=rate,
                input=True,
                frames_per_buffer=chunk
            )
            logger.info(f"Audio stream opened: {rate}Hz, {channels} channel(s)")
        except Exception as e:
            logger.error(f"Error opening audio stream: {str(e)}")
            self.is_running = False
            return
        
        # Process audio in chunks
        while self.is_running:
            try:
                # Read audio data
                data = self.stream.read(chunk, exception_on_overflow=False)
                audio_data = np.frombuffer(data, dtype=np.int16)
                
                # Process the audio data (simple amplitude-based detection for now)
                if self._process_audio(audio_data):
                    logger.info("Audio trigger detected")
                    # Yield to the main thread to prevent CPU hogging
                    time.sleep(0.01)
            except Exception as e:
                logger.error(f"Error processing audio: {str(e)}")
                time.sleep(0.1)  # Avoid tight loop on errors
    
    def _process_audio(self, audio_data: np.ndarray) -> bool:
        """
        Process audio data to detect triggers.
        
        Args:
            audio_data: Numpy array of audio samples
            
        Returns:
            True if a trigger was detected, False otherwise
        """
        # Simple amplitude-based detection
        amplitude = np.abs(audio_data).mean()
        
        # Add frequency domain analysis for better trigger detection
        if len(audio_data) >= self.config.chunk_size:
            # Perform FFT if we have enough data
            try:
                # Calculate power spectrum
                spectrum = np.abs(np.fft.rfft(audio_data * np.hanning(len(audio_data))))
                
                # Check if certain frequency bands exceed thresholds
                # This could help distinguish human voice from background noise
                voice_band = spectrum[50:300].mean()  # Approximate human voice frequency range
                
                # Could return True based on combined amplitude and frequency analysis
                return amplitude > self.config.amplitude_threshold or voice_band > (self.config.amplitude_threshold * 0.7)
            except Exception:
                # Fall back to simple amplitude check on error
                pass
        
        return amplitude > self.config.amplitude_threshold


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
        self.audio_monitor = AudioMonitor(self.config)
        
        # Keep track of detected triggers
        self.last_trigger_time = 0
        self.is_running = False
    
    def start(self) -> None:
        """Start the awareness node."""
        if self.is_running:
            logger.warning("Awareness node is already running")
            return
            
        self.is_running = True
        
        # Start audio monitoring if enabled
        if self.config.audio_enabled:
            self.audio_monitor.start()
        
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
        self.audio_monitor.stop()
        
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
