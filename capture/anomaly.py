"""
Anomaly detection for Noisy Pi.
Uses a rolling window approach - no artificial hourly boundaries.
"""
import time
from collections import deque
from typing import Optional

from . import config
from . import db


class RollingBaseline:
    """
    Maintains a rolling window baseline for anomaly detection.
    No hourly buckets - just a continuous moving average.
    """
    
    def __init__(self, window_size: int = 100):
        """
        Args:
            window_size: Number of recent measurements to keep in memory
        """
        self.window_size = window_size
        self.values = deque(maxlen=window_size)
        self.initialized = False
        self._cached_stats = None
        self._cache_valid_count = 0
    
    def add_value(self, mean_db: float):
        """Add a new measurement to the rolling window."""
        if mean_db is None:
            return
        self.values.append(mean_db)
        # Invalidate cache
        self._cached_stats = None
    
    def _compute_stats(self) -> tuple:
        """Compute mean and standard deviation of current window."""
        if len(self.values) < 5:
            return None, None
        
        # Use cached value if still valid
        if self._cached_stats and self._cache_valid_count == len(self.values):
            return self._cached_stats
        
        values = list(self.values)
        n = len(values)
        mean = sum(values) / n
        
        # Sample standard deviation
        if n > 1:
            variance = sum((x - mean) ** 2 for x in values) / (n - 1)
            std = variance ** 0.5
        else:
            std = 10.0  # Default
        
        self._cached_stats = (mean, std)
        self._cache_valid_count = n
        
        return mean, std
    
    def get_baseline(self) -> tuple:
        """Get current baseline (mean, std, sample_count)."""
        mean, std = self._compute_stats()
        return mean, std, len(self.values)
    
    def compute_anomaly_score(self, mean_db: float) -> float:
        """
        Compute anomaly score using Z-score against rolling baseline.
        
        Args:
            mean_db: Current measurement's mean dB level
        
        Returns:
            Z-score. Higher = more anomalous. Values > 2.0 are flagged.
        """
        if mean_db is None:
            return 0.0
        
        baseline_mean, baseline_std = self._compute_stats()
        
        if baseline_mean is None:
            # Not enough data yet
            return 0.0
        
        if baseline_std < 0.5:
            baseline_std = 0.5  # Minimum std to avoid over-sensitivity
        
        z_score = abs(mean_db - baseline_mean) / baseline_std
        
        return float(round(z_score, 2))
    
    def load_from_db(self, lookback_hours: int = 24):
        """
        Load recent measurements from database to initialize the window.
        Called once at startup.
        """
        if self.initialized:
            return
        
        try:
            measurements = db.get_recent_measurements_for_baseline(
                limit=self.window_size,
                max_age_hours=lookback_hours
            )
            
            for m in reversed(measurements):  # Oldest first
                if m['mean_db'] is not None:
                    self.values.append(m['mean_db'])
            
            self.initialized = True
            
            if len(self.values) > 0:
                mean, std = self._compute_stats()
                print(f"Loaded {len(self.values)} measurements into baseline "
                      f"(mean={mean:.1f}dB, std={std:.1f}dB)")
        except Exception as e:
            print(f"Could not load baseline from DB: {e}")
            self.initialized = True  # Don't retry


# Global instance
rolling_baseline = RollingBaseline(
    window_size=config.get_config_value('baseline_window_size', 100)
)


def get_anomaly_score(timestamp: int, mean_db: float, band_levels: dict = None) -> float:
    """Get anomaly score for a measurement using rolling baseline."""
    # Initialize from DB on first call
    if not rolling_baseline.initialized:
        rolling_baseline.load_from_db()
    
    return rolling_baseline.compute_anomaly_score(mean_db)


def trigger_baseline_update(mean_db: float):
    """Add measurement to rolling baseline."""
    rolling_baseline.add_value(mean_db)



