# Noisy Pi

**Ambient noise monitoring for Raspberry Pi, designed to run alongside BirdNET-Pi.**

Noisy Pi captures audio from BirdNET-Pi's Icecast stream, analyzes noise levels and frequency content, detects anomalies, and provides a web dashboard for visualization.

## Features

### Core Features
- **Non-interfering**: Uses BirdNET-Pi's existing Icecast audio stream
- **Noise metrics**: Mean, max, and min dB levels
- **Percentiles**: L10, L50, L90 statistical levels
- **7 Frequency bands**: Detailed coverage from 0-24kHz
- **Spectral features**: Centroid, flatness, dominant frequency
- **Silence detection**: Percentage of quiet time per sample
- **Full spectrogram**: 256-bin FFT with 10 snapshots per sample

### Anomaly Detection
- **Statistical baseline**: Learns normal patterns per hour/day-of-week
- **Z-score anomalies**: Flags measurements that deviate significantly
- **Visual indicators**: Anomalies highlighted in dashboard
- **Optional snippets**: Save audio clips of anomalies for review (privacy-aware, opt-in)

### Dashboard

The dashboard has multiple tabs with rich visualization:

#### Dashboard Tab
- **Stats overview**: Current level, max, min, centroid, silence %, anomaly count
- **Sound levels chart**: Time-series of mean, max, and L90 levels
- **7-band heatmap**: Clickable frequency vs time visualization
- **Anomaly chart**: Z-score timeline with threshold indicator
- **Recent measurements**: Table with inline annotation editing
- **Audio snippets**: Playback and management of captured anomalies

#### Spectrogram Tab
- **Full spectrogram view**: Detailed band-based visualization
- **Colormap selection**: Viridis, Plasma, Inferno, Magma
- **Measurement detail**: Click to view individual sample spectrum
- **Detailed metrics**: Centroid, flatness, dominant frequency

#### Statistics Tab
- **Period selection**: Today, This Week, This Month, All Time
- **Stats cards**: Aggregate metrics for selected period
- **Hourly pattern**: Bar chart of today's activity
- **Weekly baseline heatmap**: Learned patterns by hour and day

#### History Tab
- **Date range picker**: Select custom date ranges
- **Historical charts**: Visualize past data
- **Data export**: Download CSV for external analysis
- **Full data table**: All 7 frequency bands displayed

### Settings
- **Anomaly threshold**: Adjust Z-score sensitivity
- **Audio snippets**: Enable/disable anomaly recording
- **Snippet duration**: Configure recording length
- **Auto-refresh interval**: Set dashboard update frequency

## Requirements

- Raspberry Pi with BirdNET-Pi installed and running
- BirdNET-Pi's Icecast stream enabled (default configuration)
- ffmpeg, PHP, SQLite3, Python3

## Installation

```bash
curl -s https://raw.githubusercontent.com/andjar/noisy_pi/main/install.sh | sudo bash
```

Or clone and install:

```bash
git clone https://github.com/andjar/noisy_pi.git
cd noisy_pi
sudo bash install.sh
```

## Usage

After installation, access the dashboard at:
- `http://your-pi-hostname.local:8080`
- `http://your-pi-ip:8080`

### Commands

```bash
# Check service status
sudo systemctl status noisy-capture
sudo systemctl status noisy-web

# View logs
journalctl -u noisy-capture -f
tail -f /var/log/noisy-pi/capture.log

# Query database
sqlite3 /var/lib/noisy-pi/noisy.db "SELECT * FROM measurements ORDER BY id DESC LIMIT 10;"

# Restart services
sudo systemctl restart noisy-capture
sudo systemctl restart noisy-web
```

## Configuration

Edit `/opt/noisy-pi/config/noisy.json`:

```json
{
    "icecast_url": "http://localhost:8000/stream",
    "sample_rate": 48000,
    "sample_duration": 30,
    "sample_interval": 30,
    "anomaly_threshold": 2.5,
    "baseline_min_samples": 100,
    "snippet_enabled": false,
    "snippet_duration": 5,
    "refresh_interval": 30,
    "web_port": 8080
}
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `icecast_url` | `http://localhost:8000/stream` | BirdNET-Pi Icecast stream URL |
| `sample_duration` | `30` | Duration of each audio sample (seconds) |
| `sample_interval` | `30` | Time between samples (seconds) |
| `anomaly_threshold` | `2.5` | Z-score threshold for anomaly detection |
| `baseline_min_samples` | `100` | Samples needed before baseline is valid |
| `snippet_enabled` | `false` | Save audio clips of anomalies |
| `snippet_duration` | `5` | Length of anomaly audio clips (seconds) |
| `refresh_interval` | `30` | Dashboard auto-refresh interval (seconds) |
| `web_port` | `8080` | Dashboard port (auto-adjusted if busy) |

Changes require service restart: `sudo systemctl restart noisy-capture`

## How It Works

```
Microphone → BirdNET-Pi → PulseAudio → Icecast Stream
                                            ↓
                                      Noisy Pi (ffmpeg)
                                            ↓
                              Analyze → Store → Dashboard
```

Noisy Pi uses ffmpeg to capture audio from BirdNET-Pi's Icecast stream:
- Raw audio capture for FFT spectral analysis
- `silencedetect` filter for quiet periods
- 256-bin FFT for full 0-24kHz coverage

This approach ensures zero interference with BirdNET-Pi's operation.

### Metrics Captured

Each measurement (every 30 seconds by default) includes:

| Metric | Description |
|--------|-------------|
| `mean_db` | Average sound level (dB) |
| `max_db` | Peak sound level (dB) |
| `min_db` | Minimum sound level (dB) |
| `l10_db` | Level exceeded 10% of time |
| `l50_db` | Median level (50th percentile) |
| `l90_db` | Background level (90th percentile) |
| `band_0_200` | Sub-bass/bass (0-200 Hz) |
| `band_200_500` | Low-mid (200-500 Hz) |
| `band_500_1k` | Mid (500-1000 Hz) |
| `band_1k_2k` | Upper-mid (1-2 kHz) |
| `band_2k_4k` | Presence (2-4 kHz) |
| `band_4k_8k` | Brilliance (4-8 kHz) |
| `band_8k_24k` | Air/ultrasonic (8-24 kHz) |
| `spectral_centroid` | "Brightness" of sound (Hz) |
| `spectral_flatness` | Tonal vs noise-like (0-1) |
| `dominant_freq` | Strongest frequency (Hz) |
| `silence_pct` | Percentage of silence |
| `anomaly_score` | Statistical deviation score |

## Uninstallation

```bash
sudo bash /opt/noisy-pi/uninstall.sh
```

## Database Schema

```sql
measurements:
  - id, timestamp, unix_time
  - mean_db, max_db, min_db
  - l10_db, l50_db, l90_db
  - band_0_200, band_200_500, band_500_1k, band_1k_2k
  - band_2k_4k, band_4k_8k, band_8k_24k
  - spectral_centroid, spectral_flatness, dominant_freq
  - silence_pct, dynamic_range
  - anomaly_score, annotation
  - sample_seconds, status
  - spectrogram (BLOB), spectrogram_snapshots, spectrogram_bins

baseline:
  - day_of_week (0-6), hour (0-23)
  - mean_db_avg, mean_db_std, samples

snippets:
  - id, timestamp, measurement_id
  - filename, anomaly_score
```

## Privacy Considerations

- **No continuous recording**: Only extracted features are stored
- **Snippets opt-in**: Audio clips are disabled by default
- **Local storage**: All data stays on your Raspberry Pi
- **User control**: Delete snippets anytime via dashboard
- **Manual annotation**: Add context to measurements for review

## Troubleshooting

### No data appearing
```bash
# Check capture service
sudo systemctl status noisy-capture

# Check Icecast stream is available
ffmpeg -hide_banner -i http://localhost:8000/stream -t 3 -f null - 2>&1 | grep -E "Audio|Duration"

# View capture logs
journalctl -u noisy-capture -n 50
```

### Dashboard not loading
```bash
# Check web service
sudo systemctl status noisy-web

# Check PHP
php -v

# Try different port if 8080 is busy
cat /opt/noisy-pi/config/noisy.json | grep web_port
```

### High anomaly scores
- The baseline needs time to learn (100+ samples)
- Check if actual noise events occurred
- Adjust `anomaly_threshold` if too sensitive

## License

MIT License - see LICENSE file.

## Credits

Inspired by [BirdNET-Pi](https://github.com/Nachtzuster/BirdNET-Pi).
