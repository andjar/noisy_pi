"""
Detailed spectral analysis for Noisy Pi.
Captures 256-bin FFT spectrograms at 3-second intervals.
"""
import numpy as np
import subprocess
import tempfile
import os
import zlib
from typing import Optional, Tuple, List

from . import config


def capture_audio_segment(url: str, duration: float, sample_rate: int = 48000) -> Optional[np.ndarray]:
    """
    Capture audio segment from Icecast stream to numpy array.
    
    Returns mono audio as float32 array, or None on failure.
    """
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        temp_path = f.name
    
    try:
        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-nostdin',
            '-y',
            '-i', url,
            '-t', str(duration),
            '-ac', '1',  # Mono
            '-ar', str(sample_rate),
            '-f', 'wav',
            temp_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=duration + 10)
        
        if result.returncode != 0:
            return None
        
        # Read the WAV file
        import wave
        with wave.open(temp_path, 'rb') as wf:
            n_frames = wf.getnframes()
            audio_bytes = wf.readframes(n_frames)
            audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        return audio
        
    except Exception as e:
        return None
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def compute_spectrogram(
    audio: np.ndarray,
    sample_rate: int = 48000,
    fft_size: int = 512,
    hop_size: int = None,
    n_bins: int = 256
) -> np.ndarray:
    """
    Compute spectrogram from audio using FFT.
    
    Args:
        audio: Audio samples as float32 array
        sample_rate: Sample rate in Hz
        fft_size: FFT window size
        hop_size: Samples between frames (default: fft_size // 2)
        n_bins: Number of frequency bins to return (up to fft_size // 2)
    
    Returns:
        2D array of shape (n_frames, n_bins) with dB values
    """
    if hop_size is None:
        hop_size = fft_size // 2
    
    # Ensure we don't request more bins than available
    n_bins = min(n_bins, fft_size // 2)
    
    # Number of frames
    n_frames = (len(audio) - fft_size) // hop_size + 1
    
    if n_frames <= 0:
        return np.array([])
    
    # Hann window
    window = np.hanning(fft_size)
    
    # Compute spectrogram
    spectrogram = np.zeros((n_frames, n_bins))
    
    for i in range(n_frames):
        start = i * hop_size
        frame = audio[start:start + fft_size] * window
        
        # FFT
        spectrum = np.fft.rfft(frame)
        magnitude = np.abs(spectrum[:n_bins])
        
        # Convert to dB
        magnitude = np.maximum(magnitude, 1e-10)  # Avoid log(0)
        spectrogram[i] = 20 * np.log10(magnitude)
    
    return spectrogram


def compute_snapshot_spectrogram(
    url: str,
    snapshot_duration: float = 3.0,
    n_snapshots: int = 10,
    sample_rate: int = 48000,
    n_bins: int = 256
) -> Tuple[Optional[np.ndarray], dict]:
    """
    Capture audio and compute spectrogram snapshots.
    
    Captures (snapshot_duration * n_snapshots) seconds of audio
    and computes average spectrum for each snapshot period.
    
    Returns:
        Tuple of (spectrogram array, metrics dict)
        Spectrogram shape: (n_snapshots, n_bins)
    """
    total_duration = snapshot_duration * n_snapshots
    
    # Capture audio
    audio = capture_audio_segment(url, total_duration, sample_rate)
    
    if audio is None or len(audio) < sample_rate:
        return None, {}
    
    samples_per_snapshot = int(snapshot_duration * sample_rate)
    
    # Compute spectrogram for each snapshot
    snapshots = []
    snapshot_metrics = []
    
    for i in range(n_snapshots):
        start = i * samples_per_snapshot
        end = start + samples_per_snapshot
        
        if end > len(audio):
            break
        
        segment = audio[start:end]
        
        # Compute spectrogram for this segment
        spec = compute_spectrogram(segment, sample_rate, fft_size=512, n_bins=n_bins)
        
        if len(spec) > 0:
            # Average across time to get single spectrum for this snapshot
            avg_spectrum = np.mean(spec, axis=0)
            snapshots.append(avg_spectrum)
            
            # Compute metrics for this snapshot
            rms = np.sqrt(np.mean(segment ** 2))
            db = 20 * np.log10(max(rms, 1e-10))
            snapshot_metrics.append({'db': db})
    
    if not snapshots:
        return None, {}
    
    spectrogram = np.array(snapshots)
    
    # Compute overall metrics
    metrics = {
        'spectral_centroid': compute_spectral_centroid(spectrogram, sample_rate, n_bins),
        'spectral_flatness': compute_spectral_flatness(spectrogram),
        'dominant_freq': compute_dominant_frequency(spectrogram, sample_rate, n_bins),
        'snapshot_metrics': snapshot_metrics
    }
    
    return spectrogram, metrics


def compute_spectral_centroid(spectrogram: np.ndarray, sample_rate: int, n_bins: int) -> float:
    """Compute spectral centroid (center of mass of spectrum)."""
    # Convert from dB to linear
    linear = 10 ** (spectrogram / 20)
    
    # Frequency bins
    freqs = np.linspace(0, sample_rate / 2, n_bins)
    
    # Average spectrum
    avg_spectrum = np.mean(linear, axis=0)
    
    # Centroid
    if np.sum(avg_spectrum) > 0:
        centroid = np.sum(freqs * avg_spectrum) / np.sum(avg_spectrum)
        return float(centroid)
    return 0.0


def compute_spectral_flatness(spectrogram: np.ndarray) -> float:
    """
    Compute spectral flatness (tonality).
    High value = noise-like, Low value = tonal.
    """
    # Convert from dB to linear
    linear = 10 ** (spectrogram / 20)
    avg_spectrum = np.mean(linear, axis=0)
    
    # Geometric mean / Arithmetic mean
    geo_mean = np.exp(np.mean(np.log(avg_spectrum + 1e-10)))
    arith_mean = np.mean(avg_spectrum)
    
    if arith_mean > 0:
        return float(geo_mean / arith_mean)
    return 0.0


def compute_dominant_frequency(spectrogram: np.ndarray, sample_rate: int, n_bins: int) -> float:
    """Compute dominant frequency (frequency with highest energy)."""
    # Convert from dB to linear
    linear = 10 ** (spectrogram / 20)
    avg_spectrum = np.mean(linear, axis=0)
    
    # Frequency bins
    freqs = np.linspace(0, sample_rate / 2, n_bins)
    
    # Find peak
    peak_idx = np.argmax(avg_spectrum)
    return float(freqs[peak_idx])


def get_band_energies(spectrogram: np.ndarray, sample_rate: int, n_bins: int) -> dict:
    """
    Extract energy in multiple frequency bands from spectrogram.
    
    Returns dict with band levels in dB.
    Bands cover the full spectrum from 0 to Nyquist (24kHz for 48kHz sample rate).
    """
    freqs = np.linspace(0, sample_rate / 2, n_bins)
    
    # Convert from dB to linear, average, then back to dB
    linear = 10 ** (spectrogram / 20)
    avg_spectrum = np.mean(linear, axis=0)
    
    def band_energy(f_low, f_high):
        """Get average energy in frequency band."""
        mask = (freqs >= f_low) & (freqs < f_high)
        if np.any(mask):
            energy = np.mean(avg_spectrum[mask])
            return float(20 * np.log10(max(energy, 1e-10)))
        return -90.0
    
    # 12 frequency bands covering 0-24kHz for detailed analysis
    bands = {
        # Original 7 bands (for backward compatibility)
        'band_0_200': band_energy(0, 200),          # Sub-bass/bass
        'band_200_500': band_energy(200, 500),      # Low-mid
        'band_500_1k': band_energy(500, 1000),      # Mid
        'band_1k_2k': band_energy(1000, 2000),      # Upper-mid
        'band_2k_4k': band_energy(2000, 4000),      # Presence
        'band_4k_8k': band_energy(4000, 8000),      # Brilliance
        'band_8k_24k': band_energy(8000, 24000),    # Air/ultrasonic
        
        # Additional 5 bands for finer resolution
        'band_0_100': band_energy(0, 100),          # Infrasound/rumble
        'band_100_300': band_energy(100, 300),      # Bass
        'band_300_800': band_energy(300, 800),      # Low-mid detail
        'band_800_1500': band_energy(800, 1500),    # Mid detail
        'band_1500_3k': band_energy(1500, 3000),    # Upper-mid detail
        'band_3k_6k': band_energy(3000, 6000),      # Presence detail
        'band_6k_12k': band_energy(6000, 12000),    # Brilliance detail
        'band_12k_24k': band_energy(12000, 24000),  # Ultrasonic
    }
    
    return bands


def quantize_spectrogram(spectrogram: np.ndarray, db_min: float = -90, db_max: float = 10) -> bytes:
    """
    Quantize spectrogram to 8-bit and compress with zlib.
    
    Args:
        spectrogram: 2D array of dB values (n_snapshots x n_bins)
        db_min: Minimum dB value (maps to 0)
        db_max: Maximum dB value (maps to 255)
    
    Returns:
        Compressed bytes
    """
    # Clip to range
    clipped = np.clip(spectrogram, db_min, db_max)
    
    # Normalize to 0-255
    normalized = (clipped - db_min) / (db_max - db_min)
    quantized = (normalized * 255).astype(np.uint8)
    
    # Compress
    return zlib.compress(quantized.tobytes(), level=6)


def dequantize_spectrogram(
    data: bytes,
    n_snapshots: int,
    n_bins: int,
    db_min: float = -90,
    db_max: float = 10
) -> np.ndarray:
    """
    Decompress and dequantize spectrogram back to dB values.
    """
    # Decompress
    decompressed = zlib.decompress(data)
    
    # Reconstruct array
    quantized = np.frombuffer(decompressed, dtype=np.uint8)
    quantized = quantized.reshape((n_snapshots, n_bins))
    
    # Dequantize
    normalized = quantized.astype(np.float32) / 255.0
    spectrogram = normalized * (db_max - db_min) + db_min
    
    return spectrogram
