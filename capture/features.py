"""
Audio feature extraction for Noisy Pi.
"""
import numpy as np
from typing import Tuple, List

from . import config


def quantize_spectrum(spectrum: np.ndarray, db_min: float = -90, db_max: float = 10) -> bytes:
    """
    Quantize spectrum to 8-bit values for storage.
    
    Args:
        spectrum: Array of dB values
        db_min: Minimum dB value (maps to 0)
        db_max: Maximum dB value (maps to 255)
    
    Returns:
        Bytes of 8-bit quantized values
    """
    # Clip to range
    clipped = np.clip(spectrum, db_min, db_max)
    
    # Map to 0-255
    normalized = (clipped - db_min) / (db_max - db_min)
    quantized = (normalized * 255).astype(np.uint8)
    
    return quantized.tobytes()


def dequantize_spectrum(data: bytes, db_min: float = -90, db_max: float = 10) -> np.ndarray:
    """
    Dequantize 8-bit spectrum back to dB values.
    
    Args:
        data: Bytes of 8-bit quantized values
        db_min: Minimum dB value
        db_max: Maximum dB value
    
    Returns:
        Array of dB values
    """
    quantized = np.frombuffer(data, dtype=np.uint8)
    normalized = quantized.astype(np.float32) / 255.0
    spectrum = normalized * (db_max - db_min) + db_min
    
    return spectrum


def compute_percentiles(values: List[float]) -> Tuple[float, float, float]:
    """
    Compute L10, L50, L90 percentiles from a list of dB values.
    
    L10: Level exceeded 10% of the time (high)
    L50: Level exceeded 50% of the time (median)
    L90: Level exceeded 90% of the time (background)
    
    Returns:
        Tuple of (L10, L50, L90)
    """
    if not values:
        return None, None, None
    
    arr = np.array(values)
    l10 = float(np.percentile(arr, 90))  # Exceeded 10% = 90th percentile
    l50 = float(np.percentile(arr, 50))  # Median
    l90 = float(np.percentile(arr, 10))  # Exceeded 90% = 10th percentile
    
    return l10, l50, l90


def estimate_dominant_frequency(band_low: float, band_mid: float, band_high: float) -> float:
    """
    Estimate dominant frequency band from band levels.
    
    Returns approximate center frequency of loudest band.
    """
    if band_low is None or band_mid is None or band_high is None:
        return None
    
    bands = [
        (band_low, 100),    # Low band center ~100 Hz
        (band_mid, 1000),   # Mid band center ~1000 Hz
        (band_high, 5000),  # High band center ~5000 Hz
    ]
    
    # Find band with highest level
    max_level = max(bands, key=lambda x: x[0] if x[0] is not None else -999)
    return float(max_level[1])


def db_to_linear(db: float) -> float:
    """Convert dB to linear scale."""
    return 10 ** (db / 20)


def linear_to_db(linear: float) -> float:
    """Convert linear to dB scale."""
    if linear <= 0:
        return -90.0
    return 20 * np.log10(linear)



