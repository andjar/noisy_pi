"""
Anomaly detection for Noisy Pi.

Hybrid approach:
1. Rolling window for recent baseline (no artificial hourly boundaries)
2. Time-of-day profile that learns seasonal patterns (morning commute, night quiet)
3. Anomaly = deviation from expected level for this time of day
"""
import math
import time
from collections import deque
from datetime import datetime
from typing import Optional, Tuple

from . import config
from . import db


class TimeOfDayProfile:
    """
    Learns time-of-day patterns using smooth interpolation.
    Uses 48 bins (30-minute intervals) with Gaussian smoothing to avoid sharp edges.
    """
    
    def __init__(self, n_bins: int = 48, smoothing_sigma: float = 2.0):
        """
        Args:
            n_bins: Number of time bins per day (48 = 30 min each)
            smoothing_sigma: Gaussian smoothing width in bins
        """
        self.n_bins = n_bins
        self.smoothing_sigma = smoothing_sigma
        self.bin_minutes = 24 * 60 // n_bins  # 30 minutes per bin
        
        # Each bin stores: (sum_values, sum_squared, count)
        self.bins = [(0.0, 0.0, 0) for _ in range(n_bins)]
        self.initialized = False
    
    def _time_to_bin(self, timestamp: int) -> Tuple[int, float]:
        """
        Convert timestamp to bin index and fractional position.
        Returns (bin_index, fraction_into_bin)
        """
        dt = datetime.fromtimestamp(timestamp)
        minutes = dt.hour * 60 + dt.minute
        exact_bin = minutes / self.bin_minutes
        bin_idx = int(exact_bin) % self.n_bins
        fraction = exact_bin - int(exact_bin)
        return bin_idx, fraction
    
    def _gaussian_weight(self, distance: float) -> float:
        """Gaussian weight for smoothing."""
        return math.exp(-0.5 * (distance / self.smoothing_sigma) ** 2)
    
    def add_sample(self, timestamp: int, mean_db: float):
        """Add a sample, updating nearby bins with Gaussian weighting."""
        if mean_db is None:
            return
        
        bin_idx, fraction = self._time_to_bin(timestamp)
        
        # Update this bin and neighbors with Gaussian weights
        for offset in range(-3, 4):  # -3 to +3 bins
            target_bin = (bin_idx + offset) % self.n_bins
            
            # Distance considers fractional position
            distance = abs(offset - fraction + 0.5)
            weight = self._gaussian_weight(distance)
            
            if weight > 0.01:  # Skip negligible weights
                s, sq, c = self.bins[target_bin]
                self.bins[target_bin] = (
                    s + mean_db * weight,
                    sq + (mean_db ** 2) * weight,
                    c + weight
                )
    
    def get_expected(self, timestamp: int) -> Tuple[Optional[float], Optional[float]]:
        """
        Get expected mean and std for a given time.
        Uses smooth interpolation between bins.
        """
        bin_idx, fraction = self._time_to_bin(timestamp)
        
        # Interpolate between bins using Gaussian weights
        weighted_sum = 0.0
        weighted_sq_sum = 0.0
        total_weight = 0.0
        
        for offset in range(-3, 4):
            target_bin = (bin_idx + offset) % self.n_bins
            s, sq, c = self.bins[target_bin]
            
            if c < 1:
                continue
            
            distance = abs(offset - fraction + 0.5)
            weight = self._gaussian_weight(distance) * c  # Weight by count too
            
            bin_mean = s / c
            weighted_sum += bin_mean * weight
            weighted_sq_sum += (sq / c) * weight
            total_weight += weight
        
        if total_weight < 5:  # Not enough data
            return None, None
        
        expected_mean = weighted_sum / total_weight
        expected_var = max(0, weighted_sq_sum / total_weight - expected_mean ** 2)
        expected_std = math.sqrt(expected_var) if expected_var > 0 else 5.0
        
        return expected_mean, expected_std
    
    def load_from_db(self):
        """Load historical data to build time-of-day profile."""
        if self.initialized:
            return
        
        try:
            # Load last 7 days of data
            measurements = db.get_recent_measurements_for_baseline(
                limit=5000,
                max_age_hours=24 * 7
            )
            
            for m in measurements:
                if m['mean_db'] is not None:
                    self.add_sample(m['unix_time'], m['mean_db'])
            
            self.initialized = True
            
            # Count bins with data
            bins_with_data = sum(1 for _, _, c in self.bins if c >= 5)
            print(f"Time profile: loaded {len(measurements)} samples, "
                  f"{bins_with_data}/{self.n_bins} bins active")
            
        except Exception as e:
            print(f"Could not load time profile: {e}")
            self.initialized = True


class RollingBaseline:
    """
    Maintains a rolling window for recent baseline.
    Used to detect sudden changes from recent levels.
    """
    
    def __init__(self, window_size: int = 50):
        self.window_size = window_size
        self.values = deque(maxlen=window_size)
        self._cached_stats = None
    
    def add_value(self, mean_db: float):
        if mean_db is None:
            return
        self.values.append(mean_db)
        self._cached_stats = None
    
    def get_stats(self) -> Tuple[Optional[float], Optional[float]]:
        """Get mean and std of rolling window."""
        if len(self.values) < 5:
            return None, None
        
        if self._cached_stats:
            return self._cached_stats
        
        values = list(self.values)
        n = len(values)
        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / (n - 1) if n > 1 else 25
        std = math.sqrt(variance)
        
        self._cached_stats = (mean, std)
        return mean, std


class HybridAnomalyDetector:
    """
    Combines rolling baseline with time-of-day patterns.
    
    Anomaly score considers:
    1. Deviation from recent levels (rolling baseline)
    2. Deviation from expected level for this time of day
    """
    
    def __init__(self):
        self.time_profile = TimeOfDayProfile(n_bins=48, smoothing_sigma=2.0)
        self.rolling = RollingBaseline(
            window_size=config.get_config_value('baseline_window_size', 50)
        )
        self.initialized = False
        
        # Weight for time-of-day vs rolling (0=only rolling, 1=only time)
        # Start with more rolling weight, increase time weight as profile matures
        self.time_weight = 0.5
    
    def initialize(self):
        """Load historical data."""
        if self.initialized:
            return
        
        self.time_profile.load_from_db()
        
        # Load recent values into rolling window
        try:
            recent = db.get_recent_measurements_for_baseline(
                limit=self.rolling.window_size,
                max_age_hours=6
            )
            for m in reversed(recent):
                if m['mean_db'] is not None:
                    self.rolling.add_value(m['mean_db'])
        except Exception:
            pass
        
        self.initialized = True
    
    def add_measurement(self, timestamp: int, mean_db: float):
        """Update both baselines with new measurement."""
        if mean_db is None:
            return
        self.rolling.add_value(mean_db)
        self.time_profile.add_sample(timestamp, mean_db)
    
    def compute_anomaly_score(self, timestamp: int, mean_db: float) -> float:
        """
        Compute anomaly score combining rolling and time-of-day baselines.
        
        Returns the higher of:
        - Z-score vs rolling baseline (catches sudden changes)
        - Z-score vs time-of-day expected (catches unusual for this time)
        
        With some weighting to balance the two.
        """
        if mean_db is None:
            return 0.0
        
        scores = []
        
        # Rolling baseline score
        rolling_mean, rolling_std = self.rolling.get_stats()
        if rolling_mean is not None:
            std = max(rolling_std, 1.0)
            rolling_zscore = abs(mean_db - rolling_mean) / std
            scores.append(('rolling', rolling_zscore))
        
        # Time-of-day score
        time_mean, time_std = self.time_profile.get_expected(timestamp)
        if time_mean is not None:
            std = max(time_std, 1.0)
            time_zscore = abs(mean_db - time_mean) / std
            scores.append(('time', time_zscore))
        
        if not scores:
            return 0.0
        
        if len(scores) == 1:
            return float(round(scores[0][1], 2))
        
        # Combine scores: use weighted average, biased toward the higher one
        rolling_score = next((s for n, s in scores if n == 'rolling'), 0)
        time_score = next((s for n, s in scores if n == 'time'), 0)
        
        # Take the higher score but dampen it slightly with the lower
        # This means: unusual for EITHER recent OR time-of-day triggers anomaly
        max_score = max(rolling_score, time_score)
        min_score = min(rolling_score, time_score)
        
        # Combined: 70% max + 30% min
        combined = 0.7 * max_score + 0.3 * min_score
        
        return float(round(combined, 2))


# Global instance
detector = HybridAnomalyDetector()


def get_anomaly_score(timestamp: int, mean_db: float, band_levels: dict = None) -> float:
    """Get anomaly score using hybrid detection."""
    if not detector.initialized:
        detector.initialize()
    
    return detector.compute_anomaly_score(timestamp, mean_db)


def trigger_baseline_update(mean_db: float):
    """Update baselines with new measurement."""
    timestamp = int(time.time())
    detector.add_measurement(timestamp, mean_db)



