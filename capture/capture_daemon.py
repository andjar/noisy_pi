#!/usr/bin/env python3
"""
Noisy Pi capture daemon.
Supports two modes:
1. File-watching mode (default): Analyzes BirdNET-Pi's pre-recorded WAV files
2. Direct capture mode: Captures audio directly from PulseAudio (may conflict with BirdNET-Pi)
"""
import sys
import time
import signal
import logging
import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from config import (
    SAMPLE_RATE, CHANNELS, BLOCK_SIZE, MEASUREMENT_INTERVAL,
    LOG_DIR, DATA_DIR, SNIPPET_DIR, get_config,
    FILE_WATCH_MODE, BIRDNET_STREAM_DIR, FILE_WATCH_POLL_INTERVAL, FILE_SETTLE_TIME
)
from db import (
    init_database, insert_measurement, 
    is_file_processed, mark_file_processed, cleanup_old_processed_files
)
from features import IntervalProcessor, compute_fft_spectrum, compute_a_weighted_level
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


class FileWatchCapture:
    """
    File-watching capture mode.
    Monitors BirdNET-Pi's StreamData directory and analyzes new WAV files.
    
    Advantages:
    - No audio device conflicts with BirdNET-Pi
    - Lower resource usage (no real-time audio processing)
    - Processes the same audio that BirdNET analyzes
    
    The files are READ-ONLY - we never modify or delete them.
    """
    
    def __init__(self, debug: bool = False):
        self.logger = setup_logging(debug)
        self.running = False
        
        # Load config
        self.config = get_config()
        self.stream_dir = Path(self.config.get('birdnet_stream_dir', str(BIRDNET_STREAM_DIR)))
        self.poll_interval = self.config.get('file_watch_poll_interval', FILE_WATCH_POLL_INTERVAL)
        self.settle_time = self.config.get('file_settle_time', FILE_SETTLE_TIME)
        
        # Snippet settings
        self.save_snippets = self.config.get('save_anomaly_snippets', False)
        self.snippet_threshold = self.config.get('snippet_threshold', 2.5)
        
        # Statistics
        self.files_processed = 0
        self.measurements_stored = 0
        self.errors = 0
        self.last_baseline_update = 0
        self.baseline_update_interval = 3600  # Update baseline hourly
        
    def _is_file_ready(self, filepath: Path) -> bool:
        """
        Check if a file is ready for processing.
        A file is ready if it hasn't been modified in the last settle_time seconds.
        """
        try:
            mtime = filepath.stat().st_mtime
            age = time.time() - mtime
            return age >= self.settle_time
        except (OSError, FileNotFoundError):
            return False
    
    def _read_wav_file(self, filepath: Path) -> Optional[tuple]:
        """
        Read a WAV file and return audio samples and sample rate.
        Returns None if file can't be read.
        """
        try:
            import soundfile as sf
            audio, sr = sf.read(str(filepath), dtype='float32')
            
            # Convert to mono if stereo
            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)
            
            return audio, sr
        except Exception as e:
            self.logger.warning(f"Failed to read {filepath.name}: {e}")
            return None
    
    def _extract_timestamp_from_filename(self, filename: str) -> Optional[int]:
        """
        Extract timestamp from BirdNET filename format.
        Format: 2025-12-29-birdnet-15:42:36.wav
        """
        try:
            # Remove .wav extension
            name = filename.replace('.wav', '')
            # Split by -birdnet-
            parts = name.split('-birdnet-')
            if len(parts) == 2:
                date_part = parts[0]  # 2025-12-29
                time_part = parts[1]  # 15:42:36
                
                # Parse date and time
                dt = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M:%S")
                return int(dt.timestamp())
        except Exception:
            pass
        
        # Fallback: use file modification time
        return None
    
    def _process_wav_file(self, filepath: Path) -> bool:
        """
        Process a single WAV file and store measurements.
        Returns True if successful.
        """
        try:
            # Read the WAV file
            result = self._read_wav_file(filepath)
            if result is None:
                return False
            
            audio, sr = result
            file_size = filepath.stat().st_size
            
            # Get timestamp from filename or file mtime
            timestamp = self._extract_timestamp_from_filename(filepath.name)
            if timestamp is None:
                timestamp = int(filepath.stat().st_mtime)
            
            # Resample if necessary (BirdNET typically uses 48kHz)
            if sr != SAMPLE_RATE:
                self.logger.debug(f"Resampling from {sr}Hz to {SAMPLE_RATE}Hz")
                # Simple resampling by interpolation
                duration = len(audio) / sr
                num_samples = int(duration * SAMPLE_RATE)
                indices = np.linspace(0, len(audio) - 1, num_samples)
                audio = np.interp(indices, np.arange(len(audio)), audio)
            
            # Process into snapshots (like IntervalProcessor but for file-based audio)
            snapshot_duration = self.config.get('snapshot_duration', 3.0)
            snapshots_per_interval = self.config.get('snapshots_per_interval', 10)
            samples_per_snapshot = int(SAMPLE_RATE * snapshot_duration)
            
            # Calculate how many complete snapshots we can extract
            total_samples = len(audio)
            max_snapshots = total_samples // samples_per_snapshot
            num_snapshots = min(max_snapshots, snapshots_per_interval)
            
            if num_snapshots < 1:
                self.logger.debug(f"File too short: {filepath.name} ({len(audio)} samples)")
                # Still mark as processed to avoid retrying
                mark_file_processed(filepath.name, file_size)
                return True
            
            # Extract features from each snapshot
            from features import compute_fft_spectrum, compute_a_weighted_level, quantize_spectrum
            from features import compute_spectral_centroid, compute_spectral_flatness, compute_dominant_frequency
            from features import compute_percentiles, count_events
            
            spectra = []
            levels = []
            
            for i in range(num_snapshots):
                start = i * samples_per_snapshot
                end = start + samples_per_snapshot
                snapshot = audio[start:end]
                
                # Compute spectrum and level
                spectrum = compute_fft_spectrum(snapshot)
                level = compute_a_weighted_level(snapshot)
                
                spectra.append(spectrum)
                levels.append(level)
            
            levels = np.array(levels)
            
            # Aggregate metrics
            laeq = float(10 * np.log10(np.mean(10 ** (levels / 10))))  # Energy average
            lmax = float(np.max(levels))
            lmin = float(np.min(levels))
            l10, l50, l90 = compute_percentiles(levels)
            
            # Spectral features (from average spectrum)
            avg_spectrum = np.mean(spectra, axis=0)
            spectral_centroid = compute_spectral_centroid(avg_spectrum)
            spectral_flatness = compute_spectral_flatness(avg_spectrum)
            dominant_freq = compute_dominant_frequency(avg_spectrum)
            
            # Event count
            event_count = count_events(audio[:num_snapshots * samples_per_snapshot])
            
            # Pack spectrogram data
            spectrogram_data = b''.join(quantize_spectrum(s) for s in spectra)
            
            # Pad spectrogram if we have fewer snapshots than expected
            if num_snapshots < snapshots_per_interval:
                # Pad with zeros (silence)
                padding = b'\x00' * (256 * (snapshots_per_interval - num_snapshots))
                spectrogram_data += padding
            
            # Compute anomaly score
            anomaly_score = get_anomaly_score(timestamp, laeq, avg_spectrum)
            
            # Save snippet if anomaly exceeds threshold
            snippet_path = None
            if self.save_snippets and anomaly_score >= self.snippet_threshold:
                snippet_path = self._save_snippet(filepath, timestamp, anomaly_score)
            
            # Store in database
            measurement_id = insert_measurement(
                timestamp=timestamp,
                laeq=laeq,
                lmax=lmax,
                lmin=lmin,
                l10=l10,
                l50=l50,
                l90=l90,
                spectral_centroid=spectral_centroid,
                spectral_flatness=spectral_flatness,
                dominant_freq=dominant_freq,
                event_count=event_count,
                spectrogram=spectrogram_data,
                anomaly_score=anomaly_score,
                snippet_path=snippet_path
            )
            
            # Mark file as processed
            mark_file_processed(filepath.name, file_size, measurement_id)
            
            self.files_processed += 1
            self.measurements_stored += 1
            
            # Log summary
            dt = datetime.fromtimestamp(timestamp)
            anomaly_flag = " [ANOMALY]" if anomaly_score > 2.0 else ""
            self.logger.info(
                f"{dt.strftime('%H:%M:%S')} | "
                f"LAeq: {laeq:.1f} dB | "
                f"Lmax: {lmax:.1f} dB | "
                f"Events: {event_count} | "
                f"Centroid: {spectral_centroid:.0f} Hz | "
                f"Anomaly: {anomaly_score:.2f}{anomaly_flag} | "
                f"File: {filepath.name}"
            )
            
            return True
            
        except Exception as e:
            self.errors += 1
            self.logger.error(f"Error processing {filepath.name}: {e}", exc_info=True)
            return False
    
    def _save_snippet(self, source_file: Path, timestamp: int, anomaly_score: float) -> Optional[str]:
        """
        Save a copy of the anomaly audio file as a snippet.
        Since we're processing WAV files, we just copy the relevant portion.
        """
        try:
            import soundfile as sf
            import shutil
            
            # Ensure snippet directory exists
            SNIPPET_DIR.mkdir(parents=True, exist_ok=True)
            
            # Generate filename
            dt = datetime.fromtimestamp(timestamp)
            filename = f"anomaly_{dt.strftime('%Y%m%d_%H%M%S')}_{anomaly_score:.1f}.ogg"
            filepath = SNIPPET_DIR / filename
            
            # Read the source file and save as OGG
            audio, sr = sf.read(str(source_file), dtype='float32')
            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)
            
            # Take just the first 5 seconds
            snippet_duration = self.config.get('snippet_duration', 5.0)
            snippet_samples = int(sr * snippet_duration)
            audio = audio[:snippet_samples]
            
            # Save as OGG Vorbis
            sf.write(str(filepath), audio, sr, format='OGG', subtype='VORBIS')
            
            self.logger.info(f"Saved snippet: {filename}")
            return str(filepath)
            
        except Exception as e:
            self.logger.error(f"Failed to save snippet: {e}")
            return None
    
    def _scan_directory(self):
        """Scan the stream directory for new WAV files."""
        if not self.stream_dir.exists():
            self.logger.warning(f"Stream directory not found: {self.stream_dir}")
            return []
        
        wav_files = []
        for f in self.stream_dir.glob("*.wav"):
            if f.is_file() and not is_file_processed(f.name):
                if self._is_file_ready(f):
                    wav_files.append(f)
        
        return sorted(wav_files, key=lambda f: f.stat().st_mtime)
    
    def run(self):
        """Start the file-watching capture daemon."""
        self.logger.info("=" * 60)
        self.logger.info("Noisy Pi Capture Daemon starting (FILE-WATCH MODE)")
        self.logger.info("=" * 60)
        
        # Initialize database
        init_database()
        
        # Check for soundfile
        try:
            import soundfile as sf
            self.logger.info(f"soundfile version: {sf.__version__}")
        except ImportError:
            self.logger.error("soundfile not installed. Run: pip3 install soundfile")
            return 1
        
        self.logger.info(f"Watching directory: {self.stream_dir}")
        self.logger.info(f"Poll interval: {self.poll_interval}s, Settle time: {self.settle_time}s")
        
        if self.save_snippets:
            self.logger.info(f"Anomaly snippets: ENABLED (threshold={self.snippet_threshold})")
        else:
            self.logger.info("Anomaly snippets: DISABLED")
        
        # Setup signal handlers
        self.running = True
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        last_cleanup = time.time()
        cleanup_interval = 86400  # Daily cleanup
        
        self.logger.info("File-watch capture started. Press Ctrl+C to stop.")
        
        while self.running:
            try:
                # Scan for new files
                new_files = self._scan_directory()
                
                for wav_file in new_files:
                    if not self.running:
                        break
                    self._process_wav_file(wav_file)
                
                # Periodic baseline update
                now = time.time()
                if (now - self.last_baseline_update) > self.baseline_update_interval:
                    trigger_baseline_update()
                    self.last_baseline_update = now
                
                # Periodic cleanup of old processed file records
                if (now - last_cleanup) > cleanup_interval:
                    cleanup_old_processed_files(days=7)
                    last_cleanup = now
                
            except Exception as e:
                self.errors += 1
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
            
            # Wait before next scan
            time.sleep(self.poll_interval)
        
        self.logger.info("Capture daemon stopped.")
        self.logger.info(f"Files processed: {self.files_processed}")
        self.logger.info(f"Measurements stored: {self.measurements_stored}")
        self.logger.info(f"Errors: {self.errors}")
        
        return 0
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False


class DirectCaptureDaemon:
    """
    Direct audio capture mode.
    Captures audio directly from PulseAudio (may conflict with BirdNET-Pi).
    
    NOTE: This mode may not work if BirdNET-Pi is using the audio device.
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
        import sounddevice as sd
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
        import sounddevice as sd
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
            self.snippet_buffer[:] = audio[-self.snippet_buffer_size:]
            self.snippet_buffer_pos = 0
        else:
            end_pos = self.snippet_buffer_pos + samples_to_add
            if end_pos <= self.snippet_buffer_size:
                self.snippet_buffer[self.snippet_buffer_pos:end_pos] = audio
                self.snippet_buffer_pos = end_pos % self.snippet_buffer_size
            else:
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
            
            # Save snippet if anomaly exceeds threshold
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
            self.processor.reset()
            self.interval_start_time = int(time.time())
    
    def _save_snippet(self, timestamp: int, anomaly_score: float) -> str:
        """Save audio snippet for anomaly."""
        try:
            import soundfile as sf
            
            SNIPPET_DIR.mkdir(parents=True, exist_ok=True)
            
            snippet_samples = int(SAMPLE_RATE * self.snippet_duration)
            
            if self.snippet_buffer_pos >= snippet_samples:
                audio = self.snippet_buffer[self.snippet_buffer_pos - snippet_samples:self.snippet_buffer_pos]
            else:
                first_part = self.snippet_buffer[-(snippet_samples - self.snippet_buffer_pos):]
                second_part = self.snippet_buffer[:self.snippet_buffer_pos]
                audio = np.concatenate([first_part, second_part])
            
            dt = datetime.fromtimestamp(timestamp)
            filename = f"anomaly_{dt.strftime('%Y%m%d_%H%M%S')}_{anomaly_score:.1f}.ogg"
            filepath = SNIPPET_DIR / filename
            
            sf.write(str(filepath), audio, SAMPLE_RATE, format='OGG', subtype='VORBIS')
            
            self.snippets_saved += 1
            self.logger.info(f"Saved snippet: {filename}")
            
            return str(filepath)
            
        except ImportError:
            self.logger.warning("soundfile not installed - cannot save snippets")
            return None
        except Exception as e:
            self.logger.error(f"Failed to save snippet: {e}")
            return None
    
    def run(self):
        """Start the direct capture daemon."""
        import sounddevice as sd
        
        self.logger.info("=" * 60)
        self.logger.info("Noisy Pi Capture Daemon starting (DIRECT CAPTURE MODE)")
        self.logger.info("=" * 60)
        self.logger.warning("Direct capture may conflict with BirdNET-Pi!")
        
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
        
        if self.save_snippets:
            self.logger.info(f"Anomaly snippets: ENABLED (threshold={self.snippet_threshold})")
        else:
            self.logger.info("Anomaly snippets: DISABLED")
        
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
        '--mode', '-m',
        choices=['file-watch', 'direct'],
        default=None,
        help="Capture mode: 'file-watch' (analyze BirdNET files) or 'direct' (capture audio directly)"
    )
    parser.add_argument(
        '--device', '-d',
        help="Audio input device (index or name) - only for direct mode"
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
    
    # List devices if requested
    if args.list_devices:
        try:
            import sounddevice as sd
            daemon = DirectCaptureDaemon(debug=args.debug)
            daemon.list_devices()
            return 0
        except ImportError:
            print("Error: sounddevice not installed")
            return 1
    
    # Determine mode
    config = get_config()
    if args.mode:
        use_file_watch = (args.mode == 'file-watch')
    else:
        use_file_watch = config.get('file_watch_mode', FILE_WATCH_MODE)
    
    # Run appropriate daemon
    if use_file_watch:
        daemon = FileWatchCapture(debug=args.debug)
    else:
        try:
            import sounddevice as sd
            daemon = DirectCaptureDaemon(device=args.device, debug=args.debug)
        except ImportError:
            print("Error: sounddevice not installed. Run: pip3 install sounddevice")
            print("Or use --mode file-watch to analyze BirdNET-Pi's recordings")
            return 1
    
    return daemon.run()


if __name__ == "__main__":
    sys.exit(main())
