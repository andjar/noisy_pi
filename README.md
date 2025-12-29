# Noisy Pi

**Ambient noise monitoring for Raspberry Pi, designed to run alongside BirdNET-Pi.**

Noisy Pi captures audio from BirdNET-Pi's Icecast stream, analyzes noise levels and frequency content, detects anomalies, and provides a web dashboard for visualization.

## Features

### Core Features
- **Non-interfering**: Uses BirdNET-Pi's existing Icecast audio stream
- **Noise metrics**: Mean, max, and min dB levels
- **Percentiles**: L10, L50, L90 statistical levels
- **Frequency bands**: Low (0-200Hz), Mid (200-2000Hz), High (2000+Hz)
- **Silence detection**: Percentage of quiet time per sample
- **Spectrogram visualization**: Band-based heatmap display

### Anomaly Detection
- **Statistical baseline**: Learns normal patterns per hour/day-of-week
- **Z-score anomalies**: Flags measurements that deviate significantly
- **Visual indicators**: Anomalies highlighted in dashboard
- **Optional snippets**: Save audio clips of anomalies for review (privacy-aware, opt-in)

### Dashboard
- **Real-time charts**: Sound levels, frequency bands, anomaly scores
- **Time range selection**: 1h, 6h, 24h, 7d views
- **Hourly statistics**: Bar charts with anomaly counts
- **Data table**: Recent measurements with annotations
- **Audio playback**: Listen to captured anomaly snippets

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
    "icecast_url": "http://127.0.0.1/stream",
    "sample_rate": 48000,
    "sample_duration": 15,
    "sample_interval": 30,
    "anomaly_threshold": 2.5,
    "baseline_min_samples": 100,
    "snippet_enabled": false,
    "snippet_duration": 5,
    "web_port": 8080
}
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `icecast_url` | `http://127.0.0.1/stream` | BirdNET-Pi Icecast stream URL |
| `sample_duration` | `15` | Duration of each audio sample (seconds) |
| `sample_interval` | `30` | Time between samples (seconds) |
| `anomaly_threshold` | `2.5` | Z-score threshold for anomaly detection |
| `baseline_min_samples` | `100` | Samples needed before baseline is valid |
| `snippet_enabled` | `false` | Save audio clips of anomalies |
| `snippet_duration` | `5` | Length of anomaly audio clips (seconds) |
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
- `volumedetect` filter for dB levels
- `silencedetect` filter for quiet periods
- Bandpass filters for frequency analysis

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
| `band_low_db` | Low frequency (0-200 Hz) level |
| `band_mid_db` | Mid frequency (200-2000 Hz) level |
| `band_high_db` | High frequency (2000+ Hz) level |
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
  - band_low_db, band_mid_db, band_high_db
  - silence_pct, peak_freq_hz, crest_factor, dynamic_range
  - anomaly_score, annotation
  - sample_seconds, status, spectrogram

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

## License

MIT License - see LICENSE file.

## Credits

Inspired by [BirdNET-Pi](https://github.com/Nachtzuster/BirdNET-Pi).
