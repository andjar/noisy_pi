"""
Noisy Pi Configuration
"""
import os
import json

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get('NOISY_DATA_DIR', '/var/lib/noisy-pi')
LOG_DIR = os.environ.get('NOISY_LOG_DIR', '/var/log/noisy-pi')
CONFIG_DIR = os.environ.get('NOISY_CONFIG_DIR', '/opt/noisy-pi/config')

DB_PATH = os.path.join(DATA_DIR, 'noisy.db')
LOG_PATH = os.path.join(LOG_DIR, 'capture.log')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'noisy.json')

# Audio capture settings - ICECAST STREAM
ICECAST_URL = "http://localhost/stream"  # BirdNET-Pi's Icecast stream
SAMPLE_RATE = 48000
CHANNELS = 1  # Convert to mono for analysis

# Analysis settings
SAMPLE_DURATION = 15  # seconds per sample
SAMPLE_INTERVAL = 30  # seconds between samples (includes sample time)

# FFT settings for spectrogram
FFT_SIZE = 256
SPECTROGRAM_SNAPSHOTS = 10  # Per sample period

# Frequency bands (Hz)
BAND_LOW_MAX = 200
BAND_MID_MIN = 200
BAND_MID_MAX = 2000
BAND_HIGH_MIN = 2000

# dB mapping for quantization
DB_MIN = -90.0
DB_MAX = 10.0

# Silence detection
SILENCE_THRESHOLD_DB = -50
SILENCE_MIN_DURATION = 0.5  # seconds

# Anomaly detection
ANOMALY_THRESHOLD = 2.5  # Z-score threshold
BASELINE_MIN_SAMPLES = 100  # Minimum samples before baseline is valid

# Anomaly snippet settings
SNIPPET_ENABLED = False
SNIPPET_DURATION = 5  # seconds
SNIPPET_DIR = os.path.join(DATA_DIR, 'snippets')

# Web server
WEB_PORT = 8080


def load_runtime_config():
    """Load runtime configuration from JSON file."""
    config = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return config


def get_config_value(key, default):
    """Get a configuration value, checking runtime config first."""
    runtime = load_runtime_config()
    return runtime.get(key, default)


# Runtime-configurable values (can be overridden in noisy.json)
def get_icecast_url():
    return get_config_value('icecast_url', ICECAST_URL)

def get_sample_duration():
    return get_config_value('sample_duration', SAMPLE_DURATION)

def get_sample_interval():
    return get_config_value('sample_interval', SAMPLE_INTERVAL)

def get_anomaly_threshold():
    return get_config_value('anomaly_threshold', ANOMALY_THRESHOLD)

def get_snippet_enabled():
    return get_config_value('snippet_enabled', SNIPPET_ENABLED)

def get_baseline_min_samples():
    return get_config_value('baseline_min_samples', BASELINE_MIN_SAMPLES)
