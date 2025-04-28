#!/usr/bin/env python3
# filepath: audio_monitor.py
"""
Audio Monitoring System - Continuously monitors audio, records when sound is detected,
and transcribes the recorded audio.

This module:
1. Listens continuously for audio input
2. When the audio level rises above a threshold, starts recording
3. Records for at least 10 seconds, extending if audio continues
4. Saves recordings as MP3 files
5. Maintains a rolling buffer of the last 6 recordings (1 minute)
6. Transcribes recordings using the faster-whisper model
"""

import os
import sys
import time
import wave
import queue
import shutil
import logging
import tempfile
import threading
import collections
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Dict, Any

import numpy as np
import sounddevice as sd
import soundfile as sf
from pydub import AudioSegment
from faster_whisper import WhisperModel

# Configure logging
logger = logging.getLogger("awareness.audio")


class AudioMonitor:
    """Audio monitoring and recording system with transcription capabilities."""
    
    def __init__(self, output_dir: str = "recordings", model_path: str = "models/tiny.en"):
        """
        Initialize the audio monitor.
        
        Args:
            output_dir: Directory to store recordings
            model_path: Path to the Whisper model
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # Audio settings
        self.sample_rate = 16000  # Hz (16kHz is common for speech recognition)
        self.channels = 1  # Mono recording
        self.dtype = 'float32'  # Audio data type
        self.device = None  # Default audio device
        
        # Recording settings
        self.is_recording = False
        self.threshold = 0.02  # Noise threshold (adjust based on testing)
        self.silence_threshold = 0.01  # Level to consider as silence
        self.min_record_time = 10  # Minimum recording time in seconds
        self.silence_limit = 2.0  # Stop recording after this many seconds of silence
        self.buffer_seconds = 1.0  # Pre-recording buffer in seconds
        self.max_recordings = 6  # Maximum number of recordings to keep
        
        # Data structures
        self.recorded_chunks = []  # Chunks of recorded audio
        self.audio_queue = queue.Queue()  # Queue for audio data
        self.recording_thread = None  # Thread for recording process
        self.previous_recordings = collections.deque(maxlen=self.max_recordings)
        self.pre_buffer = collections.deque(
            maxlen=int(self.buffer_seconds * self.sample_rate)
        )
        
        # Callback functions
        self.on_recording_complete = None  # Called when a recording is complete
        self.is_monitoring = False  # Flag indicating if monitoring is active
        
        # Status tracking
        self.last_recording_duration = 0.0
        
        # Initialize the transcription model
        logger.info(f"Loading Whisper model from {model_path}...")
        try:
            model_start = time.time()
            self.model = WhisperModel(
                model_path, 
                device="cpu", 
                compute_type="float16"
            )
            logger.info(f"Model loaded in {time.time() - model_start:.2f}s")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            self.model = None
            
    def list_audio_devices(self):
        """List all available audio devices and their properties."""
        logger.info("Available audio devices:")
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            logger.info(f"[{i}] {device['name']}")
            logger.debug(f"    Channels: in={device.get('max_input_channels', 0)}, "
                         f"out={device.get('max_output_channels', 0)}")
            if device.get('max_input_channels', 0) > 0:
                logger.debug(f"    Default sample rate: {device.get('default_samplerate', 'N/A')}")
        
        default = sd.query_devices(kind='input')
        logger.info(f"Default input device: [{default['index']}] {default['name']}")
        
    def audio_callback(self, indata, frames, time_info, status):
        """
        Callback function for the audio stream.
        
        This function is called for each audio buffer captured by the stream.
        It analyzes volume levels and decides whether to start/continue recording.
        
        Args:
            indata: Input audio buffer
            frames: Number of frames
            time_info: Time info dictionary
            status: Status flag
        """
        if status:
            logger.warning(f"Audio callback status: {status}")
            
        # Calculate volume (RMS)
        volume_norm = np.linalg.norm(indata) / np.sqrt(len(indata))
        
        # Always store in pre-buffer
        self.pre_buffer.extend(indata.copy())
        
        # Debug volume levels
        if self.is_recording:
            level_indicator = f"{'#' * int(volume_norm * 100):<30}"
            logger.debug(f"Recording: {volume_norm:.4f} {level_indicator}")
            # Add to recording buffer
            self.recorded_chunks.append(indata.copy())
        else:
            # Just log the volume level periodically (not every frame to avoid log spam)
            if hasattr(self, '_log_counter'):
                self._log_counter += 1
                if self._log_counter > 20:  # Log every ~20 frames
                    level_indicator = f"{'=' * int(volume_norm * 100):<30}"
                    logger.debug(f"Listening: {volume_norm:.4f} {level_indicator}")
                    self._log_counter = 0
            else:
                self._log_counter = 0
            
            # Start recording if volume exceeds threshold
            if volume_norm > self.threshold:
                logger.info(f"Sound detected ({volume_norm:.4f}), starting recording...")
                self.is_recording = True
                self.recording_thread = threading.Thread(
                    target=self._recording_worker
                )
                self.recording_thread.daemon = True
                self.recording_thread.start()
                
                # Add the pre-buffer data to capture what led to the trigger
                for chunk in self.pre_buffer:
                    self.recorded_chunks.append(chunk)
                
    def _recording_worker(self):
        """
        Worker thread for managing the recording process.
        
        This thread monitors recording duration and silence, and decides 
        when to stop recording and save the file.
        """
        record_start = time.time()
        last_sound = time.time()
        frames_per_second = self.sample_rate / sd.default_blocksize
        silence_frames = 0
        
        logger.info("Recording thread started")
        
        try:
            while self.is_recording:
                if not self.recorded_chunks:
                    time.sleep(0.01)
                    continue
                
                # Calculate the current volume level
                chunk = self.recorded_chunks[-1]
                volume = np.linalg.norm(chunk) / np.sqrt(len(chunk))
                
                # Update timers
                current_time = time.time()
                elapsed = current_time - record_start
                
                # Detect silence
                if volume > self.silence_threshold:
                    last_sound = current_time
                    silence_frames = 0
                    logger.debug(f"Sound continuing at {elapsed:.2f}s, level: {volume:.4f}")
                else:
                    silence_frames += 1
                    silence_duration = silence_frames / frames_per_second
                    logger.debug(f"Silence for {silence_duration:.2f}s at {elapsed:.2f}s")
                
                # Check if we should stop recording
                # 1. We've recorded at least the minimum time
                # 2. AND we've had enough silence
                elapsed_since_sound = current_time - last_sound
                if (elapsed >= self.min_record_time and 
                        elapsed_since_sound >= self.silence_limit):
                    logger.info(f"Recording complete: {elapsed:.2f}s total, "
                               f"{elapsed_since_sound:.2f}s silence")
                    # Track the recording duration
                    self.last_recording_duration = elapsed
                    break
                
                # Sleep briefly to reduce CPU usage
                time.sleep(0.1)
                
            # Save the recording once finished
            self.save_recording()
            
        except Exception as e:
            logger.error(f"Error in recording thread: {e}", exc_info=True)
        finally:
            self.is_recording = False
            logger.info("Recording thread stopped")
            
    def save_recording(self):
        """Save the current recording to a file and transcribe it."""
        if not self.recorded_chunks:
            logger.warning("No audio data to save")
            return
            
        # Create a temporary WAV file
        temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_wav.close()
        
        try:
            # Save the audio data as a WAV file first
            logger.info(f"Saving temporary WAV file: {temp_wav.name}")
            data = np.concatenate(self.recorded_chunks)
            sf.write(
                temp_wav.name, 
                data, 
                self.sample_rate, 
                subtype='PCM_16',
                format='WAV'
            )
            
            # Convert to MP3
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            mp3_path = self.output_dir / f"recording_{timestamp}.mp3"
            
            logger.info(f"Converting to MP3: {mp3_path}")
            audio = AudioSegment.from_wav(temp_wav.name)
            audio.export(mp3_path, format="mp3")
            
            # Add to our list of recordings
            self.previous_recordings.append(mp3_path)
            logger.info(f"Recording saved: {mp3_path}")
            
            # Clean up older recordings if needed
            self.cleanup_old_recordings()
            
            # Transcribe the recording
            transcript = None
            if self.model is not None:
                transcript = self.transcribe_recording(mp3_path)
                
            # Call the completion callback if registered
            if self.on_recording_complete and callable(self.on_recording_complete):
                self.on_recording_complete(mp3_path, transcript)
                
        except Exception as e:
            logger.error(f"Failed to save recording: {e}", exc_info=True)
        finally:
            # Clean up the temporary file
            try:
                os.unlink(temp_wav.name)
            except:
                pass
                
        # Reset for next recording
        self.recorded_chunks = []
            
    def cleanup_old_recordings(self):
        """Ensure we don't keep too many recordings."""
        while len(self.previous_recordings) > self.max_recordings:
            old_file = self.previous_recordings.popleft()
            try:
                logger.info(f"Removing old recording: {old_file}")
                os.unlink(old_file)
            except Exception as e:
                logger.error(f"Failed to delete old recording {old_file}: {e}")
                
    def transcribe_recording(self, audio_file: Path) -> Optional[str]:
        """
        Transcribe the given audio file using the Whisper model.
        
        Args:
            audio_file: Path to the audio file to transcribe
            
        Returns:
            Transcribed text or None if transcription failed
        """
        try:
            logger.info(f"Transcribing: {audio_file}")
            start_time = time.time()
            
            # Run transcription
            segments, info = self.model.transcribe(str(audio_file))
            
            # Log results
            elapsed = time.time() - start_time
            logger.info(f"Transcription completed in {elapsed:.2f}s")
            logger.info(f"Detected language: {info.language}")
            
            # Save transcription to a text file with the same base name
            transcript_path = audio_file.with_suffix('.txt')
            
            # Process segments into a single transcript and write segments to file
            full_transcript = ""
            with open(transcript_path, 'w') as f:
                for segment in segments:
                    line = f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}"
                    logger.info(line)
                    f.write(f"{line}\n")
                    full_transcript += segment.text + " "
                    
            logger.info(f"Transcript saved to: {transcript_path}")
            return full_transcript.strip()
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            return None
            
    def start_monitoring(self, device: Optional[int] = None, duration: Optional[int] = None):
        """
        Start monitoring audio input.
        
        Args:
            device: Audio input device to use
            duration: Optional duration to monitor for (None for continuous)
        """
        if device is not None:
            self.device = device
            
        logger.info(f"Starting audio monitoring on device {self.device}")
        logger.info(f"Sample rate: {self.sample_rate}Hz, Channels: {self.channels}")
        logger.info(f"Threshold: {self.threshold}, Min recording time: {self.min_record_time}s")
        
        self.is_monitoring = True
        
        try:
            with sd.InputStream(
                device=self.device,
                channels=self.channels,
                samplerate=self.sample_rate,
                dtype=self.dtype,
                callback=self.audio_callback
            ):
                logger.info("Audio stream started")
                
                if duration is None:
                    # Run indefinitely
                    print("Monitoring audio... Press Ctrl+C to stop")
                    while self.is_monitoring:
                        time.sleep(0.1)
                else:
                    # Run for specified duration
                    logger.info(f"Will monitor for {duration} seconds")
                    time.sleep(duration)
                    
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Error during audio monitoring: {e}", exc_info=True)
        finally:
            self.is_monitoring = False
            # Ensure any ongoing recording is saved
            if self.is_recording:
                logger.info("Finalizing in-progress recording")
                self.is_recording = False
                if self.recording_thread and self.recording_thread.is_alive():
                    self.recording_thread.join(timeout=2.0)
                self.save_recording()

def main():
    """Main entry point for the script."""
    # Ensure models directory exists
    os.makedirs("models", exist_ok=True)
    
    # Check if model exists, inform user if not
    model_path = "models/tiny.en"
    if not os.path.exists(model_path):
        logger.warning(f"Model not found at {model_path}")
        logger.warning("You can download it from Hugging Face or use the download_models.py script")
        model_path = "tiny.en"  # Fallback to let faster-whisper download it
    
    # Create the monitor
    monitor = AudioMonitor(model_path=model_path)
    
    # List available audio devices
    monitor.list_audio_devices()
    
    # Optionally allow selecting a device
    try:
        device_input = input("Enter device number or press Enter for default: ").strip()
        device = int(device_input) if device_input else None
    except ValueError:
        device = None
        
    # Start monitoring
    monitor.start_monitoring(device=device)
    
if __name__ == "__main__":
    main()