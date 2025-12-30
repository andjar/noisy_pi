"""
Anomaly detection for Noisy Pi.
Builds baseline models from historical data and scores new measurements.
"""
import numpy as np
import time
from datetime import datetime
from typing import Optional, Tuple

from . import config
from . import db


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
        avg, std, samples = db.get_baseline(day_of_week, hour)
        
        if samples >= config.get_config_value('baseline_min_samples', 100):
            baseline = {
                'mean_db_avg': avg,
                'mean_db_std': std,
                'samples': samples
            }
            self.cache[cache_key] = baseline
            self.last_cache_update = now
            return baseline
        
        return None
    
    def compute_anomaly_score(
        self,
        timestamp: int,
        mean_db: float,
        band_levels: dict = None
    ) -> float:
        """
        Compute anomaly score for a measurement.
        
        Uses Z-score based on historical data for this time period.
        
        Args:
            timestamp: Unix timestamp of the measurement
            mean_db: Mean dB level
            band_levels: Optional dict with band_low_db, band_mid_db, band_high_db
        
        Returns:
            Anomaly score (Z-score). Higher = more anomalous.
            Values > 2.0 are typically flagged as anomalies.
        """
        if mean_db is None:
            return 0.0
            
        baseline = self.get_baseline_for_time(timestamp)
        
        if baseline is None:
            # Not enough data for baseline yet
            return 0.0
        
        # Level-based anomaly (Z-score)
        avg = baseline.get('mean_db_avg', -40)
        std = baseline.get('mean_db_std', 10)
        
        if std < 0.1:
            std = 0.1  # Prevent division by very small values
        
        level_zscore = abs(mean_db - avg) / std
        
        # Could add band-based anomaly detection here
        # For now, just use level
        
        return float(round(level_zscore, 2))


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
    
    def update_current_hour(self, mean_db: float):
        """Update baseline for the current day/hour with new measurement."""
        if mean_db is None:
            return
            
        dt = datetime.now()
        db.update_baseline(dt.weekday(), dt.hour, mean_db)
        self.last_update[(dt.weekday(), dt.hour)] = time.time()


# Global instances
baseline_model = BaselineModel()
baseline_updater = BaselineUpdater()


def get_anomaly_score(timestamp: int, mean_db: float, band_levels: dict = None) -> float:
    """Get anomaly score for a measurement."""
    return baseline_model.compute_anomaly_score(timestamp, mean_db, band_levels)


def trigger_baseline_update(mean_db: float):
    """Trigger baseline update for current hour."""
    baseline_updater.update_current_hour(mean_db)


