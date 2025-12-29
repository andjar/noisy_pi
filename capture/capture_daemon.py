#!/usr/bin/env python3
"""
Noisy Pi Capture Daemon

Captures audio from BirdNET-Pi's Icecast stream using ffmpeg,
analyzes it, and stores metrics in SQLite.
"""
import subprocess
import re
import time
import signal
import sys
import os
import logging
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capture import config
from capture import db
from capture import anomaly
from capture import features

# Setup logging
logger = logging.getLogger('noisy_pi')
logger.setLevel(logging.DEBUG)
logger.propagate = False

# File handler
os.makedirs(config.LOG_DIR, exist_ok=True)
file_handler = logging.FileHandler(config.LOG_PATH)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)


class IcecastCapture:
    """Captures and analyzes audio from Icecast stream using ffmpeg."""
    
    def __init__(self):
        self.running = False
        self.measurements = 0
        self.errors = 0
        self.recent_levels = []  # For percentile calculation
        
        # Get runtime config
        self.icecast_url = config.get_icecast_url()
        self.sample_duration = config.get_sample_duration()
        self.sample_interval = config.get_sample_interval()
        self.anomaly_threshold = config.get_anomaly_threshold()
        self.snippet_enabled = config.get_snippet_enabled()
        
    def _run_ffmpeg(self, extra_args: list, timeout: int = None) -> tuple:
        """
        Run ffmpeg with the Icecast stream and return stdout, stderr.
        Returns (success, stderr_output)
        """
        if timeout is None:
            timeout = self.sample_duration + 10
            
        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-nostdin',
            '-i', self.icecast_url,
            '-t', str(self.sample_duration),
            '-ac', '1',  # Convert to mono
            '-ar', str(config.SAMPLE_RATE),
        ] + extra_args + ['-f', 'null', '-']
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return True, result.stderr
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg timed out")
            return False, ""
        except Exception as e:
            logger.error(f"ffmpeg error: {e}")
            return False, ""
    
    def analyze_volume(self) -> dict:
        """Analyze volume using ffmpeg's volumedetect filter."""
        success, output = self._run_ffmpeg(['-af', 'volumedetect'])
        
        result = {'mean_db': None, 'max_db': None}
        
        if not success:
            return result
        
        # Parse mean_volume
        match = re.search(r'mean_volume:\s*([-\d.]+)\s*dB', output)
        if match:
            result['mean_db'] = float(match.group(1))
        
        # Parse max_volume
        match = re.search(r'max_volume:\s*([-\d.]+)\s*dB', output)
        if match:
            result['max_db'] = float(match.group(1))
        
        return result
    
    def analyze_silence(self) -> float:
        """Analyze silence percentage using ffmpeg's silencedetect filter."""
        af = f"silencedetect=n={config.SILENCE_THRESHOLD_DB}dB:d={config.SILENCE_MIN_DURATION}"
        success, output = self._run_ffmpeg(['-af', af])
        
        if not success:
            return None
        
        # Parse silence periods
        silence_total = 0.0
        
        # Find all silence_duration entries
        for match in re.finditer(r'silence_duration:\s*([\d.]+)', output):
            silence_total += float(match.group(1))
        
        # Handle silence that extends to end of sample
        starts = re.findall(r'silence_start:\s*([\d.]+)', output)
        ends = re.findall(r'silence_end:', output)
        if len(starts) > len(ends) and starts:
            # Last silence period extends to end
            last_start = float(starts[-1])
            silence_total += self.sample_duration - last_start
        
        # Calculate percentage
        silence_pct = min(100.0, (silence_total / self.sample_duration) * 100)
        return round(silence_pct, 2)
    
    def analyze_band(self, low_freq: int, high_freq: int = None) -> float:
        """Analyze a frequency band using bandpass filters."""
        if high_freq:
            af = f"highpass=f={low_freq},lowpass=f={high_freq},volumedetect"
        elif low_freq == 0:
            af = f"lowpass=f={config.BAND_LOW_MAX},volumedetect"
        else:
            af = f"highpass=f={low_freq},volumedetect"
        
        success, output = self._run_ffmpeg(['-af', af])
        
        if not success:
            return None
        
        match = re.search(r'mean_volume:\s*([-\d.]+)\s*dB', output)
        if match:
            return float(match.group(1))
        return None
    
    def analyze_bands(self) -> dict:
        """Analyze all frequency bands."""
        return {
            'band_low_db': self.analyze_band(0, config.BAND_LOW_MAX),
            'band_mid_db': self.analyze_band(config.BAND_MID_MIN, config.BAND_MID_MAX),
            'band_high_db': self.analyze_band(config.BAND_HIGH_MIN),
        }
    
    def update_percentiles(self, mean_db: float) -> tuple:
        """Update recent levels and calculate percentiles."""
        if mean_db is None:
            return None, None, None
        
        # Keep last 20 measurements for percentile calculation
        self.recent_levels.append(mean_db)
        if len(self.recent_levels) > 20:
            self.recent_levels.pop(0)
        
        if len(self.recent_levels) >= 5:
            return features.compute_percentiles(self.recent_levels)
        return None, None, None
    
    def save_snippet(self, measurement_id: int, anomaly_score: float):
        """Save an audio snippet for anomaly review."""
        if not self.snippet_enabled:
            return
        
        os.makedirs(config.SNIPPET_DIR, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"anomaly_{timestamp}.ogg"
        filepath = os.path.join(config.SNIPPET_DIR, filename)
        
        # Capture a short snippet in OGG format
        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-nostdin',
            '-y',  # Overwrite
            '-i', self.icecast_url,
            '-t', str(config.SNIPPET_DURATION),
            '-ac', '1',
            '-ar', '22050',  # Lower sample rate for smaller files
            '-c:a', 'libvorbis',
            '-q:a', '3',
            filepath
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, timeout=config.SNIPPET_DURATION + 10)
            db.store_snippet(timestamp, measurement_id, filename, anomaly_score)
            logger.info(f"Saved anomaly snippet: {filename}")
        except Exception as e:
            logger.error(f"Failed to save snippet: {e}")
    
    def take_sample(self) -> dict:
        """Take a complete audio sample and analyze it."""
        timestamp = datetime.now().isoformat()
        unix_time = int(time.time())
        
        logger.debug(f"Starting sample at {timestamp}")
        
        # Analyze volume
        volume = self.analyze_volume()
        mean_db = volume.get('mean_db')
        max_db = volume.get('max_db')
        
        # Estimate min_db (rough estimate)
        min_db = mean_db - 20 if mean_db else None
        
        # Calculate percentiles from recent measurements
        l10, l50, l90 = self.update_percentiles(mean_db)
        
        # Analyze silence
        silence_pct = self.analyze_silence()
        
        # Analyze frequency bands
        bands = self.analyze_bands()
        
        # Estimate dominant frequency from bands
        peak_freq = features.estimate_dominant_frequency(
            bands.get('band_low_db'),
            bands.get('band_mid_db'),
            bands.get('band_high_db')
        )
        
        # Calculate anomaly score using the anomaly module
        anomaly_score = anomaly.get_anomaly_score(
            unix_time,
            mean_db,
            bands
        )
        
        # Determine status
        status = 'ok'
        if mean_db is None:
            status = 'capture_error'
        
        # Build measurement data
        data = {
            'timestamp': timestamp,
            'unix_time': unix_time,
            'mean_db': mean_db,
            'max_db': max_db,
            'min_db': min_db,
            'l10_db': l10,
            'l50_db': l50,
            'l90_db': l90,
            'band_low_db': bands.get('band_low_db'),
            'band_mid_db': bands.get('band_mid_db'),
            'band_high_db': bands.get('band_high_db'),
            'silence_pct': silence_pct,
            'peak_freq_hz': peak_freq,
            'crest_factor': None,  # Would need detailed analysis
            'dynamic_range': (max_db - min_db) if (max_db and min_db) else None,
            'anomaly_score': anomaly_score,
            'sample_seconds': self.sample_duration,
            'status': status,
            'spectrogram': None,  # Could add compressed spectrogram later
        }
        
        return data
    
    def run(self):
        """Main capture loop."""
        self.running = True
        
        logger.info("=" * 60)
        logger.info("Noisy Pi Capture Daemon starting (ICECAST MODE)")
        logger.info("=" * 60)
        logger.info(f"Icecast URL: {self.icecast_url}")
        logger.info(f"Sample duration: {self.sample_duration}s")
        logger.info(f"Sample interval: {self.sample_interval}s")
        logger.info(f"Anomaly threshold: {self.anomaly_threshold}")
        logger.info(f"Snippets: {'ENABLED' if self.snippet_enabled else 'DISABLED'}")
        
        # Initialize database
        db.init_db()
        
        while self.running:
            start_time = time.time()
            
            try:
                # Take and analyze sample
                data = self.take_sample()
                
                # Store in database
                measurement_id = db.store_measurement(data)
                self.measurements += 1
                
                # Log result
                if data['mean_db'] is not None:
                    logger.info(
                        f"Stored #{measurement_id}: "
                        f"mean={data['mean_db']:.1f}dB, "
                        f"max={data['max_db']:.1f}dB, "
                        f"low={data['band_low_db']:.1f}dB, "
                        f"mid={data['band_mid_db']:.1f}dB, "
                        f"high={data['band_high_db']:.1f}dB, "
                        f"silence={data['silence_pct']:.0f}%, "
                        f"anomaly={data['anomaly_score']:.2f}"
                    )
                else:
                    logger.warning(f"Stored #{measurement_id}: status={data['status']}")
                
                # Update baseline for anomaly detection
                if data['status'] == 'ok' and data['mean_db'] is not None:
                    anomaly.trigger_baseline_update(data['mean_db'])
                
                # Save snippet if anomaly detected
                if data['anomaly_score'] >= self.anomaly_threshold:
                    logger.warning(f"ANOMALY detected! Score: {data['anomaly_score']:.2f}")
                    self.save_snippet(measurement_id, data['anomaly_score'])
                
            except Exception as e:
                self.errors += 1
                logger.error(f"Sample error: {e}", exc_info=True)
            
            # Calculate sleep time to maintain interval
            elapsed = time.time() - start_time
            sleep_time = max(0, self.sample_interval - elapsed)
            
            if sleep_time > 0 and self.running:
                logger.debug(f"Sleeping for {sleep_time:.1f}s")
                time.sleep(sleep_time)
        
        logger.info("Capture daemon stopped.")
        logger.info(f"Total measurements: {self.measurements}")
        logger.info(f"Total errors: {self.errors}")
    
    def stop(self):
        """Stop the capture loop."""
        self.running = False


def main():
    capture = IcecastCapture()
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        capture.stop()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    capture.run()


if __name__ == '__main__':
    main()
