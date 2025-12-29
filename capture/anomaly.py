"""
Anomaly detection for Noisy Pi.
Builds baseline models from historical data and scores new measurements.
"""
import numpy as np
import time
from datetime import datetime
from typing import Optional, Tuple

from config import ANOMALY_THRESHOLD, BASELINE_MIN_SAMPLES, FFT_BINS
from db import get_baseline, update_baseline, get_measurements
from features import quantize_spectrum, dequantize_spectrum


class BaselineModel:
    """
    Maintains baseline statistics for anomaly detection.
    Uses day-of-week and hour-of-day patterns.
    """
    
    def __init__(self):
        self.cache = {}  # Cache loaded baselines
        self.cache_ttl = 3600  # Refresh cache every hour
        self.last_cache_update = 0
    
    def _get_time_key(self, timestamp: int) -> Tuple[int, int]:
        """Get day-of-week and hour from timestamp."""
        dt = datetime.fromtimestamp(timestamp)
        return dt.weekday(), dt.hour
    
    def get_baseline_for_time(self, timestamp: int) -> Optional[dict]:
        """Get baseline data for a specific timestamp."""
        day_of_week, hour = self._get_time_key(timestamp)
        
        # Check cache
        cache_key = (day_of_week, hour)
        now = time.time()
        
        if cache_key in self.cache and (now - self.last_cache_update) < self.cache_ttl:
            return self.cache[cache_key]
        
        # Load from database
        baseline = get_baseline(day_of_week, hour)
        if baseline and baseline.get('sample_count', 0) >= BASELINE_MIN_SAMPLES:
            self.cache[cache_key] = baseline
            self.last_cache_update = now
            return baseline
        
        return None
    
    def compute_anomaly_score(
        self,
        timestamp: int,
        laeq: float,
        spectrum: np.ndarray = None
    ) -> float:
        """
        Compute anomaly score for a measurement.
        
        Uses Z-score based on historical data for this time period.
        
        Args:
            timestamp: Unix timestamp of the measurement
            laeq: A-weighted equivalent level
            spectrum: Optional spectrum for spectral anomaly detection
        
        Returns:
            Anomaly score (Z-score). Higher = more anomalous.
            Values > 2.0 are typically flagged as anomalies.
        """
        baseline = self.get_baseline_for_time(timestamp)
        
        if baseline is None:
            # Not enough data for baseline yet
            return 0.0
        
        # Level-based anomaly (Z-score)
        laeq_mean = baseline.get('laeq_mean', 0)
        laeq_std = baseline.get('laeq_std', 1)
        
        if laeq_std < 0.1:
            laeq_std = 0.1  # Prevent division by very small values
        
        level_zscore = abs(laeq - laeq_mean) / laeq_std
        
        # Spectral anomaly (if spectrum provided)
        spectral_zscore = 0.0
        if spectrum is not None and baseline.get('spectral_mean') is not None:
            spectral_mean = np.frombuffer(baseline['spectral_mean'], dtype=np.float32)
            if len(spectral_mean) == len(spectrum):
                # Euclidean distance in spectral space, normalized
                spectral_diff = np.sqrt(np.mean((spectrum - spectral_mean) ** 2))
                spectral_zscore = spectral_diff / 10.0  # Normalize roughly to Z-score scale
        
        # Combined score (weighted average)
        combined_score = 0.7 * level_zscore + 0.3 * spectral_zscore
        
        return float(combined_score)


class BaselineUpdater:
    """
    Periodically updates baseline statistics from historical data.
    """
    
    def __init__(self, lookback_days: int = 14):
        self.lookback_days = lookback_days
        self.last_update = {}  # Track last update per (day, hour)
        self.update_interval = 3600  # Update at most once per hour
    
    def should_update(self, day_of_week: int, hour: int) -> bool:
        """Check if baseline should be updated."""
        key = (day_of_week, hour)
        now = time.time()
        
        if key not in self.last_update:
            return True
        
        return (now - self.last_update[key]) > self.update_interval
    
    def update_baseline_for_hour(self, day_of_week: int, hour: int):
        """
        Update baseline statistics for a specific day/hour combination.
        
        Computes statistics from the last N days of data.
        """
        if not self.should_update(day_of_week, hour):
            return
        
        now = time.time()
        lookback_seconds = self.lookback_days * 24 * 3600
        
        # Get all measurements for this day/hour in the lookback period
        # We need to filter by day_of_week and hour after fetching
        start_time = int(now - lookback_seconds)
        end_time = int(now)
        
        measurements = get_measurements(start_time, end_time, include_spectrogram=True)
        
        # Filter to matching day/hour
        matching = []
        for m in measurements:
            dt = datetime.fromtimestamp(m['timestamp'])
            if dt.weekday() == day_of_week and dt.hour == hour:
                matching.append(m)
        
        if len(matching) < BASELINE_MIN_SAMPLES:
            return  # Not enough data
        
        # Compute statistics
        laeq_values = [m['laeq'] for m in matching if m['laeq'] is not None]
        
        if not laeq_values:
            return
        
        laeq_mean = float(np.mean(laeq_values))
        laeq_std = float(np.std(laeq_values))
        
        # Compute average spectrum
        spectra = []
        for m in matching:
            if m.get('spectrogram'):
                # Get first snapshot spectrum as representative
                spectrum = dequantize_spectrum(m['spectrogram'][:FFT_BINS])
                spectra.append(spectrum)
        
        if spectra:
            spectral_mean = np.mean(spectra, axis=0).astype(np.float32).tobytes()
        else:
            spectral_mean = None
        
        # Update database
        update_baseline(
            day_of_week=day_of_week,
            hour=hour,
            laeq_mean=laeq_mean,
            laeq_std=laeq_std,
            spectral_mean=spectral_mean,
            sample_count=len(matching)
        )
        
        self.last_update[(day_of_week, hour)] = now
    
    def update_current_hour(self):
        """Update baseline for the current day/hour."""
        dt = datetime.now()
        self.update_baseline_for_hour(dt.weekday(), dt.hour)
    
    def update_all(self):
        """Update baselines for all day/hour combinations."""
        for day in range(7):
            for hour in range(24):
                self.update_baseline_for_hour(day, hour)


# Global instances
baseline_model = BaselineModel()
baseline_updater = BaselineUpdater()


def get_anomaly_score(timestamp: int, laeq: float, spectrum: np.ndarray = None) -> float:
    """Get anomaly score for a measurement."""
    return baseline_model.compute_anomaly_score(timestamp, laeq, spectrum)


def trigger_baseline_update():
    """Trigger baseline update for current hour."""
    baseline_updater.update_current_hour()

