"""
Anomaly detection for Noisy Pi.

Hybrid approach:
1. Rolling window for recent baseline (no artificial hourly boundaries)
2. Time-of-week profile: learns day-of-week + time-of-day patterns
   (e.g., Monday 8am vs Sunday 8am)
3. Anomaly = deviation from expected level for this time of week
"""
import math
import time
from collections import deque
from datetime import datetime
from typing import Optional, Tuple

from . import config
from . import db


class TimeOfWeekProfile:
    """
    Learns time-of-week patterns (day + time) using smooth interpolation.
    
    Structure: 7 days × 48 time bins = 336 total bins
    Uses 2D Gaussian smoothing across both time and day dimensions.
    
    Smoothing behavior:
    - Adjacent time slots blend together (7:30am ↔ 8:00am)
    - Adjacent days blend together (Monday ↔ Tuesday)
    - Weekdays share patterns with each other
    - Weekends share patterns with each other
    """
    
    def __init__(self, time_bins: int = 48, time_sigma: float = 2.0, day_sigma: float = 1.0):
        """
        Args:
            time_bins: Number of time bins per day (48 = 30 min each)
            time_sigma: Gaussian smoothing width for time (in bins)
            day_sigma: Gaussian smoothing width for days
        """
        self.time_bins = time_bins
        self.time_sigma = time_sigma
        self.day_sigma = day_sigma
        self.bin_minutes = 24 * 60 // time_bins
        
        # 7 days × time_bins: each cell stores (sum, sum_squared, count)
        # Day 0 = Monday, Day 6 = Sunday
        self.bins = [[(0.0, 0.0, 0) for _ in range(time_bins)] for _ in range(7)]
        self.initialized = False
    
    def _timestamp_to_coords(self, timestamp: int) -> Tuple[int, int, float]:
        """
        Convert timestamp to (day_of_week, time_bin, time_fraction).
        """
        dt = datetime.fromtimestamp(timestamp)
        day = dt.weekday()  # 0=Monday, 6=Sunday
        minutes = dt.hour * 60 + dt.minute
        exact_bin = minutes / self.bin_minutes
        time_bin = int(exact_bin) % self.time_bins
        time_frac = exact_bin - int(exact_bin)
        return day, time_bin, time_frac
    
    def _gaussian_weight(self, time_dist: float, day_dist: float) -> float:
        """2D Gaussian weight for smoothing."""
        time_weight = math.exp(-0.5 * (time_dist / self.time_sigma) ** 2)
        day_weight = math.exp(-0.5 * (day_dist / self.day_sigma) ** 2)
        return time_weight * day_weight
    
    def _day_distance(self, day1: int, day2: int) -> float:
        """
        Compute day distance with special handling:
        - Weekdays (0-4) are closer to each other
        - Weekends (5-6) are closer to each other
        - Cross weekend/weekday has extra distance
        """
        is_weekday1 = day1 < 5
        is_weekday2 = day2 < 5
        
        # Basic circular distance
        raw_dist = min(abs(day1 - day2), 7 - abs(day1 - day2))
        
        # Add penalty for crossing weekday/weekend boundary
        if is_weekday1 != is_weekday2:
            raw_dist += 0.5  # Extra distance for weekday↔weekend
        
        return raw_dist
    
    def add_sample(self, timestamp: int, mean_db: float):
        """Add a sample, updating nearby bins with 2D Gaussian weighting."""
        if mean_db is None:
            return
        
        day, time_bin, time_frac = self._timestamp_to_coords(timestamp)
        
        # Update nearby bins in both dimensions
        for day_offset in range(-2, 3):  # -2 to +2 days
            target_day = (day + day_offset) % 7
            day_dist = self._day_distance(day, target_day)
            
            for time_offset in range(-3, 4):  # -3 to +3 time bins
                target_time = (time_bin + time_offset) % self.time_bins
                time_dist = abs(time_offset - time_frac + 0.5)
                
                weight = self._gaussian_weight(time_dist, day_dist)
                
                if weight > 0.01:
                    s, sq, c = self.bins[target_day][target_time]
                    self.bins[target_day][target_time] = (
                        s + mean_db * weight,
                        sq + (mean_db ** 2) * weight,
                        c + weight
                    )
    
    def get_expected(self, timestamp: int) -> Tuple[Optional[float], Optional[float]]:
        """
        Get expected mean and std for a given timestamp.
        Uses smooth 2D interpolation.
        """
        day, time_bin, time_frac = self._timestamp_to_coords(timestamp)
        
        weighted_sum = 0.0
        weighted_sq_sum = 0.0
        total_weight = 0.0
        
        for day_offset in range(-2, 3):
            target_day = (day + day_offset) % 7
            day_dist = self._day_distance(day, target_day)
            
            for time_offset in range(-3, 4):
                target_time = (time_bin + time_offset) % self.time_bins
                s, sq, c = self.bins[target_day][target_time]
                
                if c < 0.5:
                    continue
                
                time_dist = abs(time_offset - time_frac + 0.5)
                weight = self._gaussian_weight(time_dist, day_dist) * c
                
                bin_mean = s / c
                weighted_sum += bin_mean * weight
                weighted_sq_sum += (sq / c) * weight
                total_weight += weight
        
        if total_weight < 3:
            return None, None
        
        expected_mean = weighted_sum / total_weight
        expected_var = max(0, weighted_sq_sum / total_weight - expected_mean ** 2)
        expected_std = math.sqrt(expected_var) if expected_var > 0 else 5.0
        
        return expected_mean, expected_std
    
    def load_from_db(self):
        """Load historical data to build time-of-week profile."""
        if self.initialized:
            return
        
        try:
            # Load last 4 weeks of data for better day-of-week coverage
            measurements = db.get_recent_measurements_for_baseline(
                limit=10000,
                max_age_hours=24 * 28
            )
            
            for m in measurements:
                if m['mean_db'] is not None:
                    self.add_sample(m['unix_time'], m['mean_db'])
            
            self.initialized = True
            
            # Count bins with meaningful data
            bins_with_data = sum(
                1 for day_bins in self.bins 
                for _, _, c in day_bins if c >= 3
            )
            total_bins = 7 * self.time_bins
            
            print(f"Time-of-week profile: loaded {len(measurements)} samples, "
                  f"{bins_with_data}/{total_bins} bins active")
            
        except Exception as e:
            print(f"Could not load time-of-week profile: {e}")
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
    Combines rolling baseline with time-of-week patterns.
    
    Anomaly score considers:
    1. Deviation from recent levels (rolling baseline)
    2. Deviation from expected level for this day+time (catches patterns
       like "Monday 8am is loud, Sunday 8am is quiet")
    """
    
    def __init__(self):
        self.time_profile = TimeOfWeekProfile(
            time_bins=48,      # 30-minute intervals
            time_sigma=2.0,    # Smooth across ~1 hour
            day_sigma=1.0      # Smooth across adjacent days
        )
        self.rolling = RollingBaseline(
            window_size=config.get_config_value('baseline_window_size', 50)
        )
        self.initialized = False
    
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
        Compute anomaly score combining rolling and time-of-week baselines.
        
        Returns weighted combination of:
        - Z-score vs rolling baseline (catches sudden changes)
        - Z-score vs time-of-week expected (catches unusual for this day+time)
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
        
        # Time-of-week score
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
        # This means: unusual for EITHER recent OR time-of-week triggers anomaly
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



