#!/usr/bin/env python3
"""
Noisy Pi capture daemon.
Continuously captures audio from PulseAudio and extracts features.
"""
import sys
import time
import signal
import logging
import argparse
from datetime import datetime
from pathlib import Path

import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("Error: sounddevice not installed. Run: pip3 install sounddevice")
    sys.exit(1)

from config import (
    SAMPLE_RATE, CHANNELS, BLOCK_SIZE, MEASUREMENT_INTERVAL,
    LOG_DIR, DATA_DIR, SNIPPET_DIR, get_config
)
from db import init_database, insert_measurement
from features import IntervalProcessor
from anomaly import get_anomaly_score, trigger_baseline_update


# Setup logging
def setup_logging(debug: bool = False):
    """Configure logging."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    log_level = logging.DEBUG if debug else logging.INFO
    
    # Get logger for this module (not root to avoid duplicates)
    logger = logging.getLogger('noisy_pi')
    
    # Clear any existing handlers to prevent duplicates
    logger.handlers.clear()
    logger.setLevel(log_level)
    
    # File handler
    log_file = LOG_DIR / "capture.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    
    # Console handler (for systemd journal)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Prevent propagation to root logger (avoids duplicates)
    logger.propagate = False
    
    return logger


class CaptureDaemon:
    """
    Main capture daemon class.
    Handles audio capture, processing, and database storage.
    """
    
    def __init__(self, device: str = None, debug: bool = False):
        self.logger = setup_logging(debug)
        self.device = device
        self.running = False
        self.processor = IntervalProcessor()
        self.interval_start_time = None
        self.last_baseline_update = 0
        self.baseline_update_interval = 3600  # Update baseline hourly
        
        # Load config for snippet settings
        self.config = get_config()
        self.save_snippets = self.config.get('save_anomaly_snippets', False)
        self.snippet_duration = self.config.get('snippet_duration', 5.0)
        self.snippet_threshold = self.config.get('snippet_threshold', 2.5)
        
        # Rolling buffer for snippets (keeps last N seconds)
        self.snippet_buffer_size = int(SAMPLE_RATE * self.snippet_duration * 1.5)
        self.snippet_buffer = np.zeros(self.snippet_buffer_size, dtype=np.float32)
        self.snippet_buffer_pos = 0
        
        # Statistics
        self.intervals_processed = 0
        self.errors = 0
        self.snippets_saved = 0
        
    def list_devices(self):
        """List available audio devices."""
        print("\nAvailable audio devices:")
        print("-" * 60)
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            input_ch = dev['max_input_channels']
            if input_ch > 0:
                print(f"  [{i}] {dev['name']}")
                print(f"      Input channels: {input_ch}, Sample rate: {dev['default_samplerate']}")
        print("-" * 60)
        print(f"\nDefault input device: {sd.default.device[0]}")
        
    def find_monitor_source(self):
        """Find a PulseAudio monitor source."""
        devices = sd.query_devices()
        
        # Look for monitor sources (won't interfere with other apps)
        for i, dev in enumerate(devices):
            name = dev['name'].lower()
            if 'monitor' in name and dev['max_input_channels'] > 0:
                self.logger.info(f"Found monitor source: {dev['name']}")
                return i
        
        # Fallback to default input
        default = sd.default.device[0]
        if default is not None:
            self.logger.info(f"Using default input device: {devices[default]['name']}")
            return default
        
        return None
    
    def audio_callback(self, indata, frames, time_info, status):
        """Callback for audio input stream."""
        if status:
            self.logger.warning(f"Audio status: {status}")
        
        # Convert to float32 and mono if needed
        audio = indata[:, 0] if indata.ndim > 1 else indata.flatten()
        audio = audio.astype(np.float32)
        
        # Initialize interval start time
        if self.interval_start_time is None:
            self.interval_start_time = int(time.time())
        
        # Add samples to processor
        self.processor.add_samples(audio)
        
        # Update rolling buffer for snippet capture
        if self.save_snippets:
            self._update_snippet_buffer(audio)
        
        # Check if interval is complete
        if self.processor.is_complete():
            self.process_interval()
    
    def _update_snippet_buffer(self, audio: np.ndarray):
        """Update rolling buffer with new audio samples."""
        samples_to_add = len(audio)
        
        if samples_to_add >= self.snippet_buffer_size:
            # Audio is larger than buffer, just keep the end
            self.snippet_buffer[:] = audio[-self.snippet_buffer_size:]
            self.snippet_buffer_pos = 0
        else:
            # Add to circular buffer
            end_pos = self.snippet_buffer_pos + samples_to_add
            if end_pos <= self.snippet_buffer_size:
                self.snippet_buffer[self.snippet_buffer_pos:end_pos] = audio
                self.snippet_buffer_pos = end_pos % self.snippet_buffer_size
            else:
                # Wrap around
                first_part = self.snippet_buffer_size - self.snippet_buffer_pos
                self.snippet_buffer[self.snippet_buffer_pos:] = audio[:first_part]
                self.snippet_buffer[:samples_to_add - first_part] = audio[first_part:]
                self.snippet_buffer_pos = samples_to_add - first_part
    
    def process_interval(self):
        """Process a complete measurement interval."""
        try:
            timestamp = self.interval_start_time
            
            # Extract features
            features = self.processor.process()
            
            # Compute anomaly score
            avg_spectrum = np.mean(features['spectra'], axis=0)
            anomaly_score = get_anomaly_score(timestamp, features['laeq'], avg_spectrum)
            
            # Save snippet if anomaly exceeds threshold and snippets are enabled
            snippet_path = None
            if self.save_snippets and anomaly_score >= self.snippet_threshold:
                snippet_path = self._save_snippet(timestamp, anomaly_score)
            
            # Store in database
            insert_measurement(
                timestamp=timestamp,
                laeq=features['laeq'],
                lmax=features['lmax'],
                lmin=features['lmin'],
                l10=features['l10'],
                l50=features['l50'],
                l90=features['l90'],
                spectral_centroid=features['spectral_centroid'],
                spectral_flatness=features['spectral_flatness'],
                dominant_freq=features['dominant_freq'],
                event_count=features['event_count'],
                spectrogram=features['spectrogram'],
                anomaly_score=anomaly_score,
                snippet_path=snippet_path
            )
            
            self.intervals_processed += 1
            
            # Log summary
            dt = datetime.fromtimestamp(timestamp)
            anomaly_flag = " [ANOMALY]" if anomaly_score > 2.0 else ""
            snippet_flag = " [SAVED]" if snippet_path else ""
            self.logger.info(
                f"{dt.strftime('%H:%M:%S')} | "
                f"LAeq: {features['laeq']:.1f} dB | "
                f"Lmax: {features['lmax']:.1f} dB | "
                f"Events: {features['event_count']} | "
                f"Centroid: {features['spectral_centroid']:.0f} Hz | "
                f"Anomaly: {anomaly_score:.2f}{anomaly_flag}{snippet_flag}"
            )
            
            # Check if baseline update is needed
            now = time.time()
            if (now - self.last_baseline_update) > self.baseline_update_interval:
                trigger_baseline_update()
                self.last_baseline_update = now
            
        except Exception as e:
            self.errors += 1
            self.logger.error(f"Error processing interval: {e}", exc_info=True)
        
        finally:
            # Reset for next interval
            self.processor.reset()
            self.interval_start_time = int(time.time())
    
    def _save_snippet(self, timestamp: int, anomaly_score: float) -> str:
        """Save audio snippet for anomaly."""
        try:
            import soundfile as sf
            
            # Ensure snippet directory exists
            SNIPPET_DIR.mkdir(parents=True, exist_ok=True)
            
            # Get audio from rolling buffer (reorder circular buffer)
            snippet_samples = int(SAMPLE_RATE * self.snippet_duration)
            
            # Extract last N seconds from circular buffer
            if self.snippet_buffer_pos >= snippet_samples:
                audio = self.snippet_buffer[self.snippet_buffer_pos - snippet_samples:self.snippet_buffer_pos]
            else:
                # Need to wrap around
                first_part = self.snippet_buffer[-(snippet_samples - self.snippet_buffer_pos):]
                second_part = self.snippet_buffer[:self.snippet_buffer_pos]
                audio = np.concatenate([first_part, second_part])
            
            # Generate filename
            dt = datetime.fromtimestamp(timestamp)
            filename = f"anomaly_{dt.strftime('%Y%m%d_%H%M%S')}_{anomaly_score:.1f}.ogg"
            filepath = SNIPPET_DIR / filename
            
            # Save as OGG Vorbis
            sf.write(str(filepath), audio, SAMPLE_RATE, format='OGG', subtype='VORBIS')
            
            self.snippets_saved += 1
            self.logger.info(f"Saved snippet: {filename}")
            
            return str(filepath)
            
        except ImportError:
            self.logger.warning("soundfile not installed - cannot save snippets. Install with: pip3 install soundfile")
            return None
        except Exception as e:
            self.logger.error(f"Failed to save snippet: {e}")
            return None
    
    def run(self):
        """Start the capture daemon."""
        self.logger.info("=" * 60)
        self.logger.info("Noisy Pi Capture Daemon starting...")
        self.logger.info("=" * 60)
        
        # Initialize database
        init_database()
        
        # Find audio device
        if self.device is None:
            device = self.find_monitor_source()
        else:
            device = int(self.device) if self.device.isdigit() else self.device
        
        if device is None:
            self.logger.error("No audio input device found!")
            return 1
        
        device_info = sd.query_devices(device)
        self.logger.info(f"Using audio device: {device_info['name']}")
        self.logger.info(f"Sample rate: {SAMPLE_RATE} Hz")
        self.logger.info(f"Measurement interval: {MEASUREMENT_INTERVAL} seconds")
        
        # Log snippet settings
        if self.save_snippets:
            self.logger.info(f"Anomaly snippets: ENABLED (threshold={self.snippet_threshold}, duration={self.snippet_duration}s)")
        else:
            self.logger.info("Anomaly snippets: DISABLED (enable in config)")
        
        # Setup signal handlers
        self.running = True
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Start audio stream
        try:
            with sd.InputStream(
                device=device,
                channels=CHANNELS,
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                dtype=np.float32,
                callback=self.audio_callback
            ):
                self.logger.info("Audio capture started. Press Ctrl+C to stop.")
                
                while self.running:
                    time.sleep(0.1)
                
        except Exception as e:
            self.logger.error(f"Audio capture error: {e}", exc_info=True)
            return 1
        
        self.logger.info("Capture daemon stopped.")
        self.logger.info(f"Intervals processed: {self.intervals_processed}")
        self.logger.info(f"Snippets saved: {self.snippets_saved}")
        self.logger.info(f"Errors: {self.errors}")
        
        return 0
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Noisy Pi capture daemon - 24/7 ambient noise monitoring"
    )
    parser.add_argument(
        '--device', '-d',
        help="Audio input device (index or name)"
    )
    parser.add_argument(
        '--list-devices', '-l',
        action='store_true',
        help="List available audio devices and exit"
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    daemon = CaptureDaemon(device=args.device, debug=args.debug)
    
    if args.list_devices:
        daemon.list_devices()
        return 0
    
    return daemon.run()


if __name__ == "__main__":
    sys.exit(main())

