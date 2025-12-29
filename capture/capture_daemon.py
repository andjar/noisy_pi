#!/usr/bin/env python3
"""
Noisy Pi Capture Daemon

Captures audio from BirdNET-Pi's Icecast stream using ffmpeg,
performs detailed spectral analysis (256 bins, 3-second snapshots),
and stores metrics in SQLite.
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
from capture import spectral

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
        self.recent_levels = []
        
        # Get runtime config
        self.icecast_url = config.get_icecast_url()
        self.sample_interval = config.get_sample_interval()
        self.anomaly_threshold = config.get_anomaly_threshold()
        self.snippet_enabled = config.get_snippet_enabled()
        
        # Spectral analysis settings
        self.n_snapshots = 10       # 10 snapshots per sample
        self.snapshot_duration = 3.0  # 3 seconds each = 30 seconds total
        self.n_bins = 256           # FFT bins (0-24kHz with 48kHz sample rate)
        self.sample_duration = self.snapshot_duration * self.n_snapshots
        
    def _run_ffmpeg_filter(self, af: str, duration: float = None) -> tuple:
        """Run ffmpeg with a filter and return success, stderr."""
        if duration is None:
            duration = self.sample_duration
            
        cmd = [
            'ffmpeg', '-hide_banner', '-nostdin',
            '-i', self.icecast_url,
            '-t', str(duration),
            '-ac', '1', '-ar', str(config.SAMPLE_RATE),
            '-af', af,
            '-f', 'null', '-'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 15)
            return True, result.stderr
        except Exception as e:
            logger.warning(f"ffmpeg error: {e}")
            return False, ""
    
    def analyze_silence(self) -> float:
        """Analyze silence percentage."""
        af = f"silencedetect=n={config.SILENCE_THRESHOLD_DB}dB:d={config.SILENCE_MIN_DURATION}"
        success, output = self._run_ffmpeg_filter(af)
        
        if not success:
            return None
        
        silence_total = 0.0
        for match in re.finditer(r'silence_duration:\s*([\d.]+)', output):
            silence_total += float(match.group(1))
        
        starts = re.findall(r'silence_start:\s*([\d.]+)', output)
        ends = re.findall(r'silence_end:', output)
        if len(starts) > len(ends) and starts:
            silence_total += self.sample_duration - float(starts[-1])
        
        return round(min(100.0, (silence_total / self.sample_duration) * 100), 2)
    
    def update_percentiles(self, mean_db: float) -> tuple:
        """Update recent levels and calculate percentiles."""
        if mean_db is None:
            return None, None, None
        
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
        
        cmd = [
            'ffmpeg', '-hide_banner', '-nostdin', '-y',
            '-i', self.icecast_url,
            '-t', str(config.SNIPPET_DURATION),
            '-ac', '1', '-ar', '22050',
            '-c:a', 'libvorbis', '-q:a', '3',
            filepath
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, timeout=config.SNIPPET_DURATION + 10)
            db.store_snippet(timestamp, measurement_id, filename, anomaly_score)
            logger.info(f"Saved anomaly snippet: {filename}")
        except Exception as e:
            logger.error(f"Failed to save snippet: {e}")
    
    def take_sample(self) -> dict:
        """Take a complete audio sample with detailed spectral analysis."""
        timestamp = datetime.now().isoformat()
        unix_time = int(time.time())
        
        logger.debug(f"Starting sample at {timestamp}")
        
        # Initialize data dict with all fields
        data = {
            'timestamp': timestamp,
            'unix_time': unix_time,
            'mean_db': None,
            'max_db': None,
            'min_db': None,
            'l10_db': None,
            'l50_db': None,
            'l90_db': None,
            'band_0_200': None,
            'band_200_500': None,
            'band_500_1k': None,
            'band_1k_2k': None,
            'band_2k_4k': None,
            'band_4k_8k': None,
            'band_8k_24k': None,
            'spectral_centroid': None,
            'spectral_flatness': None,
            'dominant_freq': None,
            'silence_pct': None,
            'dynamic_range': None,
            'anomaly_score': 0.0,
            'sample_seconds': self.sample_duration,
            'status': 'ok',
            'spectrogram': None,
            'spectrogram_snapshots': self.n_snapshots,
            'spectrogram_bins': self.n_bins,
        }
        
        # Perform detailed spectral analysis
        # Captures 30 seconds (10 x 3s snapshots) with 256-bin FFT
        spectrogram_data, spectral_metrics = spectral.compute_snapshot_spectrogram(
            self.icecast_url,
            snapshot_duration=self.snapshot_duration,
            n_snapshots=self.n_snapshots,
            sample_rate=config.SAMPLE_RATE,
            n_bins=self.n_bins
        )
        
        if spectrogram_data is not None and len(spectrogram_data) > 0:
            # Extract 7 frequency bands
            bands = spectral.get_band_energies(spectrogram_data, config.SAMPLE_RATE, self.n_bins)
            
            data['band_0_200'] = bands.get('band_0_200')
            data['band_200_500'] = bands.get('band_200_500')
            data['band_500_1k'] = bands.get('band_500_1k')
            data['band_1k_2k'] = bands.get('band_1k_2k')
            data['band_2k_4k'] = bands.get('band_2k_4k')
            data['band_4k_8k'] = bands.get('band_4k_8k')
            data['band_8k_24k'] = bands.get('band_8k_24k')
            
            # Spectral metrics
            data['spectral_centroid'] = spectral_metrics.get('spectral_centroid')
            data['spectral_flatness'] = spectral_metrics.get('spectral_flatness')
            data['dominant_freq'] = spectral_metrics.get('dominant_freq')
            
            # Compute mean/max/min from snapshot metrics
            snapshot_dbs = [m['db'] for m in spectral_metrics.get('snapshot_metrics', []) if 'db' in m]
            if snapshot_dbs:
                data['mean_db'] = float(sum(snapshot_dbs) / len(snapshot_dbs))
                data['max_db'] = float(max(snapshot_dbs))
                data['min_db'] = float(min(snapshot_dbs))
                data['dynamic_range'] = data['max_db'] - data['min_db']
            
            # Compress and store spectrogram
            try:
                data['spectrogram'] = spectral.quantize_spectrogram(
                    spectrogram_data,
                    db_min=config.DB_MIN,
                    db_max=config.DB_MAX
                )
                data['spectrogram_snapshots'] = len(spectrogram_data)
                data['spectrogram_bins'] = spectrogram_data.shape[1] if len(spectrogram_data.shape) > 1 else self.n_bins
            except Exception as e:
                logger.warning(f"Failed to compress spectrogram: {e}")
        else:
            data['status'] = 'capture_error'
            logger.warning("Spectral analysis failed")
        
        # Analyze silence
        data['silence_pct'] = self.analyze_silence()
        
        # Calculate percentiles
        if data['mean_db'] is not None:
            l10, l50, l90 = self.update_percentiles(data['mean_db'])
            data['l10_db'] = l10
            data['l50_db'] = l50
            data['l90_db'] = l90
        
        # Calculate anomaly score
        data['anomaly_score'] = anomaly.get_anomaly_score(unix_time, data['mean_db'], None)
        
        return data
    
    def run(self):
        """Main capture loop."""
        self.running = True
        
        logger.info("=" * 60)
        logger.info("Noisy Pi Capture Daemon starting (ICECAST MODE)")
        logger.info("=" * 60)
        logger.info(f"Icecast URL: {self.icecast_url}")
        logger.info(f"Sample: {self.n_snapshots} x {self.snapshot_duration}s = {self.sample_duration}s")
        logger.info(f"FFT bins: {self.n_bins} (0-24kHz)")
        logger.info(f"Interval: {self.sample_interval}s")
        logger.info(f"Anomaly threshold: {self.anomaly_threshold}")
        logger.info(f"Snippets: {'ENABLED' if self.snippet_enabled else 'DISABLED'}")
        
        db.init_db()
        
        while self.running:
            start_time = time.time()
            
            try:
                data = self.take_sample()
                measurement_id = db.store_measurement(data)
                self.measurements += 1
                
                if data['mean_db'] is not None:
                    logger.info(
                        f"#{measurement_id}: "
                        f"mean={data['mean_db']:.1f}dB "
                        f"[{data['band_0_200']:.0f}|{data['band_200_500']:.0f}|"
                        f"{data['band_500_1k']:.0f}|{data['band_1k_2k']:.0f}|"
                        f"{data['band_2k_4k']:.0f}|{data['band_4k_8k']:.0f}|"
                        f"{data['band_8k_24k']:.0f}] "
                        f"centroid={data['spectral_centroid']:.0f}Hz "
                        f"anomaly={data['anomaly_score']:.2f}"
                    )
                else:
                    logger.warning(f"#{measurement_id}: status={data['status']}")
                
                if data['status'] == 'ok' and data['mean_db'] is not None:
                    anomaly.trigger_baseline_update(data['mean_db'])
                
                if data['anomaly_score'] >= self.anomaly_threshold:
                    logger.warning(f"ANOMALY detected! Score: {data['anomaly_score']:.2f}")
                    self.save_snippet(measurement_id, data['anomaly_score'])
                
            except Exception as e:
                self.errors += 1
                logger.error(f"Sample error: {e}", exc_info=True)
            
            elapsed = time.time() - start_time
            sleep_time = max(0, self.sample_interval - elapsed)
            
            if sleep_time > 0 and self.running:
                time.sleep(sleep_time)
        
        logger.info("Capture daemon stopped.")
        logger.info(f"Total measurements: {self.measurements}, Errors: {self.errors}")
    
    def stop(self):
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
