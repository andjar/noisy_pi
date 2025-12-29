"""
Configuration for Noisy Pi capture daemon.
"""
import os
import json
from pathlib import Path

# Paths
INSTALL_DIR = Path(os.environ.get("NOISY_PI_DIR", "/opt/noisy-pi"))
DATA_DIR = Path(os.environ.get("NOISY_PI_DATA", "/var/lib/noisy-pi"))
LOG_DIR = Path(os.environ.get("NOISY_PI_LOG", "/var/log/noisy-pi"))

# For development on Windows or non-standard setups
if not INSTALL_DIR.exists():
    INSTALL_DIR = Path(__file__).parent.parent
    DATA_DIR = INSTALL_DIR / "data"
    LOG_DIR = INSTALL_DIR / "logs"

# Database
DB_PATH = DATA_DIR / "noisy.db"

# Audio capture settings
SAMPLE_RATE = 48000  # Hz - standard for most USB mics
CHANNELS = 1  # Mono
BLOCK_SIZE = 4096  # Samples per callback

# File-watching mode (uses BirdNET-Pi's recordings instead of direct capture)
FILE_WATCH_MODE = True  # Default to file-watching to avoid audio conflicts
BIRDNET_STREAM_DIR = Path.home() / "BirdSongs" / "StreamData"
FILE_WATCH_POLL_INTERVAL = 1.0  # Seconds between directory scans
FILE_SETTLE_TIME = 2.0  # Wait for file to finish writing before processing

# Analysis settings
FFT_BINS = 256  # Number of frequency bins
SNAPSHOT_DURATION = 3.0  # Seconds per snapshot
SNAPSHOTS_PER_INTERVAL = 10  # Number of snapshots per measurement interval
MEASUREMENT_INTERVAL = SNAPSHOT_DURATION * SNAPSHOTS_PER_INTERVAL  # 30 seconds

# Frequency range (Hz)
FREQ_MIN = 0
FREQ_MAX = SAMPLE_RATE // 2  # Nyquist frequency (24kHz for 48kHz sample rate)

# dB mapping for 8-bit quantization
DB_MIN = -90.0  # Minimum dB (maps to 0)
DB_MAX = 10.0   # Maximum dB (maps to 255)

# A-weighting reference
A_WEIGHT_REF = 20e-6  # Reference pressure in Pa (20 µPa)

# Anomaly detection
ANOMALY_THRESHOLD = 2.0  # Z-score threshold for anomaly flagging
BASELINE_MIN_SAMPLES = 100  # Minimum samples before baseline is valid

# Web server
WEB_PORT = 8080

# Anomaly audio snippets (opt-in feature)
SAVE_ANOMALY_SNIPPETS = False  # Disabled by default for privacy
SNIPPET_DURATION = 5.0  # Seconds (centered on anomaly)
SNIPPET_THRESHOLD = 2.5  # Only save snippets for anomalies above this score
SNIPPET_FORMAT = 'ogg'  # OGG Vorbis for good compression
SNIPPET_DIR = DATA_DIR / "snippets"


def load_config_file():
    """Load configuration from JSON file if it exists."""
    config_file = INSTALL_DIR / "config" / "noisy.json"
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)
    return {}


def get_config():
    """Get merged configuration (defaults + file overrides)."""
    file_config = load_config_file()
    return {
        "sample_rate": file_config.get("sample_rate", SAMPLE_RATE),
        "fft_bins": file_config.get("fft_bins", FFT_BINS),
        "snapshot_duration": file_config.get("snapshot_duration", SNAPSHOT_DURATION),
        "snapshots_per_interval": file_config.get("snapshots_per_interval", SNAPSHOTS_PER_INTERVAL),
        "db_min": file_config.get("db_min", DB_MIN),
        "db_max": file_config.get("db_max", DB_MAX),
        "anomaly_threshold": file_config.get("anomaly_threshold", ANOMALY_THRESHOLD),
        "web_port": file_config.get("web_port", WEB_PORT),
        # Anomaly snippets
        "save_anomaly_snippets": file_config.get("save_anomaly_snippets", SAVE_ANOMALY_SNIPPETS),
        "snippet_duration": file_config.get("snippet_duration", SNIPPET_DURATION),
        "snippet_threshold": file_config.get("snippet_threshold", SNIPPET_THRESHOLD),
        # File-watching mode
        "file_watch_mode": file_config.get("file_watch_mode", FILE_WATCH_MODE),
        "birdnet_stream_dir": file_config.get("birdnet_stream_dir", str(BIRDNET_STREAM_DIR)),
        "file_watch_poll_interval": file_config.get("file_watch_poll_interval", FILE_WATCH_POLL_INTERVAL),
        "file_settle_time": file_config.get("file_settle_time", FILE_SETTLE_TIME),
    }

