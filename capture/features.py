"""
Audio feature extraction for Noisy Pi.
Implements 256-bin FFT with 8-bit quantization and various audio metrics.
"""
import numpy as np
from typing import Tuple, List
from config import (
    SAMPLE_RATE, FFT_BINS, DB_MIN, DB_MAX, A_WEIGHT_REF,
    SNAPSHOT_DURATION, SNAPSHOTS_PER_INTERVAL
)


# Pre-compute A-weighting coefficients for the frequency bins
def compute_a_weighting(frequencies: np.ndarray) -> np.ndarray:
    """
    Compute A-weighting coefficients for given frequencies.
    A-weighting approximates human hearing sensitivity.
    """
    f = frequencies.astype(float)
    # Avoid division by zero
    f[f == 0] = 1e-10
    
    # A-weighting formula (IEC 61672-1)
    f2 = f ** 2
    num = 12194 ** 2 * f2 ** 2
    den = ((f2 + 20.6 ** 2) * 
           np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2)) * 
           (f2 + 12194 ** 2))
    
    a_weight = num / den
    # Normalize to 0 dB at 1 kHz
    a_weight_1k = 12194 ** 2 * 1000 ** 4 / ((1000 ** 2 + 20.6 ** 2) * 
                   np.sqrt((1000 ** 2 + 107.7 ** 2) * (1000 ** 2 + 737.9 ** 2)) * 
                   (1000 ** 2 + 12194 ** 2))
    a_weight = a_weight / a_weight_1k
    
    return a_weight


# Pre-compute frequency bin centers
FREQ_BINS = np.fft.rfftfreq(FFT_BINS * 2, 1.0 / SAMPLE_RATE)[:FFT_BINS]
A_WEIGHT_COEFFS = compute_a_weighting(FREQ_BINS)


def db_to_uint8(db_value: float) -> int:
    """Convert dB value to 8-bit integer (0-255)."""
    normalized = (db_value - DB_MIN) / (DB_MAX - DB_MIN)
    clamped = max(0.0, min(1.0, normalized))
    return int(clamped * 255)


def uint8_to_db(value: int) -> float:
    """Convert 8-bit integer back to dB value."""
    normalized = value / 255.0
    return normalized * (DB_MAX - DB_MIN) + DB_MIN


def amplitude_to_db(amplitude: float, ref: float = A_WEIGHT_REF) -> float:
    """Convert amplitude to dB with reference level."""
    if amplitude <= 0:
        return DB_MIN
    db = 20 * np.log10(amplitude / ref)
    return max(DB_MIN, min(DB_MAX, db))


def compute_fft_spectrum(audio_chunk: np.ndarray) -> np.ndarray:
    """
    Compute FFT magnitude spectrum (256 bins).
    
    Args:
        audio_chunk: Audio samples for the snapshot (float32, normalized to [-1, 1])
    
    Returns:
        256-element array of magnitude values in dB
    """
    # Window the signal to reduce spectral leakage
    window = np.hanning(len(audio_chunk))
    windowed = audio_chunk * window
    
    # Compute FFT
    fft_size = FFT_BINS * 2
    if len(windowed) < fft_size:
        # Pad with zeros if needed
        windowed = np.pad(windowed, (0, fft_size - len(windowed)))
    elif len(windowed) > fft_size:
        # Truncate if too long
        windowed = windowed[:fft_size]
    
    spectrum = np.fft.rfft(windowed)[:FFT_BINS]
    magnitudes = np.abs(spectrum) / len(windowed)
    
    # Convert to dB
    db_spectrum = np.array([amplitude_to_db(m) for m in magnitudes])
    
    return db_spectrum


def compute_a_weighted_level(audio_chunk: np.ndarray) -> float:
    """
    Compute A-weighted sound level (LAeq) for an audio chunk.
    
    Args:
        audio_chunk: Audio samples (float32, normalized to [-1, 1])
    
    Returns:
        A-weighted level in dB
    """
    # Compute spectrum
    spectrum_db = compute_fft_spectrum(audio_chunk)
    
    # Convert back to linear, apply A-weighting, convert back to dB
    spectrum_linear = 10 ** (spectrum_db / 20) * A_WEIGHT_REF
    weighted = spectrum_linear * A_WEIGHT_COEFFS
    
    # RMS of weighted signal
    rms = np.sqrt(np.mean(weighted ** 2))
    
    return amplitude_to_db(rms)


def compute_percentiles(levels: np.ndarray) -> Tuple[float, float, float]:
    """
    Compute L10, L50, L90 percentile levels.
    
    L10: Level exceeded 10% of the time (loud events)
    L50: Median level
    L90: Level exceeded 90% of the time (background)
    """
    if len(levels) == 0:
        return 0.0, 0.0, 0.0
    
    l10 = float(np.percentile(levels, 90))  # Exceeded 10% = 90th percentile
    l50 = float(np.percentile(levels, 50))
    l90 = float(np.percentile(levels, 10))  # Exceeded 90% = 10th percentile
    
    return l10, l50, l90


def compute_spectral_centroid(spectrum_db: np.ndarray) -> float:
    """
    Compute spectral centroid (brightness) of the spectrum.
    
    Returns:
        Centroid frequency in Hz
    """
    # Convert to linear scale for centroid calculation
    spectrum_linear = 10 ** (spectrum_db / 20)
    
    total = np.sum(spectrum_linear)
    if total == 0:
        return 0.0
    
    centroid = np.sum(FREQ_BINS * spectrum_linear) / total
    return float(centroid)


def compute_spectral_flatness(spectrum_db: np.ndarray) -> float:
    """
    Compute spectral flatness (tonality).
    
    Values close to 1 = noise-like (flat spectrum)
    Values close to 0 = tonal (peaky spectrum)
    """
    # Convert to linear scale
    spectrum_linear = 10 ** (spectrum_db / 20)
    spectrum_linear = spectrum_linear[spectrum_linear > 0]  # Remove zeros
    
    if len(spectrum_linear) == 0:
        return 0.0
    
    # Geometric mean / arithmetic mean
    geometric_mean = np.exp(np.mean(np.log(spectrum_linear + 1e-10)))
    arithmetic_mean = np.mean(spectrum_linear)
    
    if arithmetic_mean == 0:
        return 0.0
    
    flatness = geometric_mean / arithmetic_mean
    return float(min(1.0, flatness))


def compute_dominant_frequency(spectrum_db: np.ndarray) -> int:
    """
    Find the dominant (peak) frequency.
    
    Returns:
        Dominant frequency in Hz
    """
    peak_idx = np.argmax(spectrum_db)
    return int(FREQ_BINS[peak_idx])


def count_events(audio_samples: np.ndarray, threshold_db: float = -30.0) -> int:
    """
    Count distinct sound events (onsets) in the audio.
    Simple onset detection based on energy threshold crossings.
    
    Args:
        audio_samples: Audio samples for the interval
        threshold_db: Threshold in dB for event detection
    
    Returns:
        Number of detected events
    """
    # Compute short-term energy in 100ms windows
    window_size = int(SAMPLE_RATE * 0.1)
    num_windows = len(audio_samples) // window_size
    
    if num_windows == 0:
        return 0
    
    energies = []
    for i in range(num_windows):
        start = i * window_size
        chunk = audio_samples[start:start + window_size]
        rms = np.sqrt(np.mean(chunk ** 2))
        energies.append(amplitude_to_db(rms))
    
    energies = np.array(energies)
    
    # Count threshold crossings (rising edges)
    above_threshold = energies > threshold_db
    crossings = np.diff(above_threshold.astype(int))
    events = np.sum(crossings == 1)  # Rising edges
    
    return int(events)


def quantize_spectrum(spectrum_db: np.ndarray) -> bytes:
    """
    Quantize spectrum to 8-bit values.
    
    Args:
        spectrum_db: 256-element array of dB values
    
    Returns:
        256 bytes representing the quantized spectrum
    """
    quantized = np.array([db_to_uint8(db) for db in spectrum_db], dtype=np.uint8)
    return quantized.tobytes()


def dequantize_spectrum(data: bytes) -> np.ndarray:
    """
    Convert quantized spectrum back to dB values.
    
    Args:
        data: 256 bytes of quantized spectrum
    
    Returns:
        256-element array of dB values
    """
    quantized = np.frombuffer(data, dtype=np.uint8)
    return np.array([uint8_to_db(v) for v in quantized])


class IntervalProcessor:
    """
    Process a 30-second measurement interval.
    Collects 10 snapshots of 3 seconds each.
    """
    
    def __init__(self):
        self.samples_per_snapshot = int(SAMPLE_RATE * SNAPSHOT_DURATION)
        self.samples_per_interval = self.samples_per_snapshot * SNAPSHOTS_PER_INTERVAL
        self.reset()
    
    def reset(self):
        """Reset for a new interval."""
        self.audio_buffer = []
        self.snapshot_spectra = []
        self.snapshot_levels = []
        self.total_samples = 0
    
    def add_samples(self, samples: np.ndarray):
        """Add audio samples to the buffer."""
        self.audio_buffer.append(samples)
        self.total_samples += len(samples)
    
    def is_complete(self) -> bool:
        """Check if we have enough samples for a complete interval."""
        return self.total_samples >= self.samples_per_interval
    
    def process(self) -> dict:
        """
        Process the complete interval and extract all features.
        
        Returns:
            Dictionary with all computed features
        """
        # Concatenate all samples
        all_samples = np.concatenate(self.audio_buffer)[:self.samples_per_interval]
        
        # Process each snapshot
        spectra = []
        levels = []
        
        for i in range(SNAPSHOTS_PER_INTERVAL):
            start = i * self.samples_per_snapshot
            end = start + self.samples_per_snapshot
            snapshot = all_samples[start:end]
            
            # Compute spectrum for this snapshot
            spectrum = compute_fft_spectrum(snapshot)
            spectra.append(spectrum)
            
            # Compute A-weighted level
            level = compute_a_weighted_level(snapshot)
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
        event_count = count_events(all_samples)
        
        # Pack spectrogram data (256 bins x 10 snapshots = 2560 bytes)
        spectrogram_data = b''.join(quantize_spectrum(s) for s in spectra)
        
        return {
            'laeq': laeq,
            'lmax': lmax,
            'lmin': lmin,
            'l10': l10,
            'l50': l50,
            'l90': l90,
            'spectral_centroid': spectral_centroid,
            'spectral_flatness': spectral_flatness,
            'dominant_freq': dominant_freq,
            'event_count': event_count,
            'spectrogram': spectrogram_data,
            'spectra': spectra,  # Keep for anomaly detection
            'levels': levels,
        }


def unpack_spectrogram(data: bytes, num_snapshots: int = SNAPSHOTS_PER_INTERVAL) -> List[np.ndarray]:
    """
    Unpack spectrogram blob into list of spectra.
    
    Args:
        data: Packed spectrogram data
        num_snapshots: Number of snapshots in the data
    
    Returns:
        List of spectrum arrays (dB values)
    """
    spectra = []
    for i in range(num_snapshots):
        start = i * FFT_BINS
        end = start + FFT_BINS
        spectrum = dequantize_spectrum(data[start:end])
        spectra.append(spectrum)
    return spectra

