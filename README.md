# Noisy Pi

A privacy-respecting 24/7 ambient noise monitoring system for Raspberry Pi. Captures acoustic features without storing raw audio, detects anomalies, and provides a modern web dashboard.

**Designed to run alongside [BirdNET-Pi](https://github.com/Nachtzuster/BirdNET-Pi) without interference.**

## Features

- **24/7 Acoustic Monitoring** - Continuous sound level measurement with LAeq, Lmax, Lmin, and percentile levels
- **256-bin Spectrogram** - Detailed frequency analysis from 0-24kHz
- **Privacy-First Design** - Only stores acoustic features, never raw audio. 3-second averaging makes speech reconstruction impossible
- **BirdNET-Pi Integration** - Automatically analyzes BirdNET-Pi's recordings without any conflicts
- **Anomaly Detection** - Learns your soundscape patterns and flags unusual events
- **Anomaly Audio Snippets** - Optional: save short audio clips (5 seconds) when anomalies occur to identify what caused them
- **Manual Annotations** - Tag interesting events for later reference
- **Modern Dashboard** - BirdNET-Pi-inspired interface with spectrogram heatmap and time-series charts
- **Low Resource Usage** - ~3% CPU, ~40MB RAM on Pi 5 (file-watch mode)

## Screenshot

```
[Dashboard showing sound levels, spectrogram, and statistics]
```

## Requirements

- Raspberry Pi 5, 4B, or 3B+
- Raspberry Pi OS (Trixie/Bookworm) 64-bit
- USB Microphone or Sound Card
- PulseAudio (usually pre-installed)
- ~2GB storage per year of data

If you have BirdNET-Pi installed, most dependencies are already present.

## Installation

### One-liner Install

```bash
curl -s https://raw.githubusercontent.com/andjar/noisy_pi/main/install.sh | bash
```

If port 8080 is already in use (e.g., by another service), the installer will automatically try ports 8081-8085. You can also specify a port:

```bash
NOISY_PI_PORT=8090 curl -s https://raw.githubusercontent.com/andjar/noisy_pi/main/install.sh | bash
```

### Manual Install

```bash
git clone https://github.com/andjar/noisy_pi.git
cd noisy_pi
./install.sh
```

## Access

After installation:

- **Dashboard**: `http://your-pi.local:8080` or `http://<IP>:8080`

The dashboard runs on port 8080 to avoid conflicts with BirdNET-Pi (which uses port 80).

## What Gets Measured

Every 30 seconds, Noisy Pi extracts:

| Metric | Description |
|--------|-------------|
| LAeq | A-weighted equivalent continuous level |
| Lmax, Lmin | Peak and minimum levels |
| L10, L50, L90 | Statistical percentile levels |
| Spectrogram | 256 frequency bins × 10 snapshots (3s each) |
| Spectral Centroid | "Brightness" of sound (Hz) |
| Spectral Flatness | Tonal vs. noise character |
| Dominant Frequency | Strongest frequency component |
| Event Count | Number of sound onsets |
| Anomaly Score | Deviation from learned baseline |

## Privacy

Noisy Pi is designed with privacy as a core principle:

1. **No Raw Audio** - Only acoustic features are stored, never the actual sound
2. **3-Second Averaging** - Temporal resolution too coarse for speech recognition
3. **No Phase Information** - Cannot reconstruct waveforms
4. **Local Processing** - All data stays on your Pi

What CAN be inferred:
- General noise levels over time
- Presence of voices (as energy in speech band)
- Activity patterns

What CANNOT be recovered:
- Actual words spoken
- Speaker identity
- Conversation content

## Capture Modes

Noisy Pi supports two capture modes:

### File-Watch Mode (Default, Recommended)

Analyzes BirdNET-Pi's pre-recorded WAV files from `~/BirdSongs/StreamData/`. This mode:

- **Zero audio conflicts** - Never touches the microphone directly
- **Lower resource usage** - No real-time audio processing
- **Perfect synchronization** - Analyzes the exact same audio that BirdNET processes
- **Graceful handling** - If BirdNET deletes a file before we process it, we simply skip it

### Direct Capture Mode

Captures audio directly from PulseAudio. Use this if you don't have BirdNET-Pi installed.

**Warning**: May conflict with BirdNET-Pi's audio access.

To switch modes, edit the config:

```json
{
    "file_watch_mode": true,   // false for direct capture
    "birdnet_stream_dir": "/home/ubuntu/BirdSongs/StreamData"
}
```

Or use command line:
```bash
# Force file-watch mode
/opt/noisy-pi/venv/bin/python3 /opt/noisy-pi/capture/capture_daemon.py --mode file-watch

# Force direct capture mode  
/opt/noisy-pi/venv/bin/python3 /opt/noisy-pi/capture/capture_daemon.py --mode direct
```

## Configuration

Edit `/opt/noisy-pi/config/noisy.json`:

```json
{
    "sample_rate": 48000,
    "fft_bins": 256,
    "snapshot_duration": 3.0,
    "snapshots_per_interval": 10,
    "anomaly_threshold": 2.0,
    "web_port": 8080,
    
    "save_anomaly_snippets": false,
    "snippet_duration": 5.0,
    "snippet_threshold": 2.5,
    
    "file_watch_mode": true,
    "birdnet_stream_dir": "/home/ubuntu/BirdSongs/StreamData",
    "file_watch_poll_interval": 1.0,
    "file_settle_time": 2.0
}
```

Restart services after changes:
```bash
sudo systemctl restart noisy-capture noisy-web
```

## Anomaly Audio Snippets

The snippet feature allows you to save short audio clips when anomalies are detected, helping you identify what caused them.

**Settings:**
- `save_anomaly_snippets`: Enable/disable snippet saving (default: `false`)
- `snippet_duration`: Length of saved clips in seconds (default: `5.0`)
- `snippet_threshold`: Minimum anomaly score to trigger saving (default: `2.5`)

**To enable via the web interface:**
1. Go to Settings tab
2. Toggle "Enable audio snippets"
3. Adjust threshold and duration as needed
4. Click "Save Settings"
5. Restart the capture daemon

**Privacy note:** When enabled, actual audio is stored for anomaly events only. This is opt-in and disabled by default to maintain privacy-first design. Snippets are stored locally and can be deleted individually or in bulk.

## Service Management

```bash
# View logs
journalctl -u noisy-capture -f
journalctl -u noisy-web -f

# Restart services
sudo systemctl restart noisy-capture
sudo systemctl restart noisy-web

# Stop services
sudo systemctl stop noisy-capture noisy-web

# Check status
systemctl status noisy-capture noisy-web
```

## Data Storage

- **Database**: `/var/lib/noisy-pi/noisy.db` (SQLite)
- **Logs**: `/var/log/noisy-pi/`
- **Expected size**: ~2GB per year

## Uninstallation

```bash
/opt/noisy-pi/uninstall.sh
```

Or manually:
```bash
sudo systemctl stop noisy-capture noisy-web
sudo systemctl disable noisy-capture noisy-web
sudo rm -rf /opt/noisy-pi
sudo rm -f /etc/systemd/system/noisy-capture.service
sudo rm -f /etc/systemd/system/noisy-web.service
# Optionally: sudo rm -rf /var/lib/noisy-pi /var/log/noisy-pi
```

## Understanding the Spectrogram

The spectrogram shows frequency (vertical, 0-24kHz) over time (horizontal). Common patterns:

| Sound | Pattern |
|-------|---------|
| Jet plane | Low-frequency band (50-500Hz), gradual onset/decay |
| Car acceleration | Rising sweep in mid frequencies |
| Rain/storm | Broadband "white" noise across all frequencies |
| Bird chorus | Energy concentrated in 2-8kHz, intermittent |
| Traffic rumble | Persistent low-frequency energy (50-200Hz) |
| Thunder | Broadband impulse, very low frequencies dominant |

## Coexistence with BirdNET-Pi

Noisy Pi is designed to run alongside BirdNET-Pi:

- Uses port 8080 (BirdNET-Pi uses 80/443)
- **File-watch mode** (default): Analyzes BirdNET's recordings - zero audio conflicts
- **Read-only access**: Never modifies or deletes BirdNET's files
- Uses separate SQLite database
- Low resource footprint (~3% CPU in file-watch mode)

The file-watch approach means Noisy Pi processes the same audio files that BirdNET records, after they're written. This eliminates all microphone access conflicts.

## Troubleshooting

### No Measurements Being Recorded (File-Watch Mode)

```bash
# Check if BirdNET StreamData directory exists
ls -la ~/BirdSongs/StreamData/

# Check recent WAV files
find ~/BirdSongs/StreamData -name "*.wav" -mmin -5 -ls

# View capture daemon logs
journalctl -u noisy-capture -f

# Check config path
cat /opt/noisy-pi/config/noisy.json | grep birdnet_stream_dir
```

### No Audio Devices Found (Direct Capture Mode)

```bash
# Check PulseAudio
pulseaudio --check
pactl list sources short

# List available devices
/opt/noisy-pi/venv/bin/python3 /opt/noisy-pi/capture/capture_daemon.py --list-devices
```

### Dashboard Not Loading

```bash
# Check web service
systemctl status noisy-web
curl http://localhost:8080/api.php?action=status
```

### High CPU Usage

This is usually during FFT processing. Should settle to ~3% on Pi 5 in file-watch mode.

## API Endpoints

The JSON API is available at `/api.php`:

- `GET /api.php?action=measurements&start=TIMESTAMP&end=TIMESTAMP`
- `GET /api.php?action=spectrogram&start=TIMESTAMP&end=TIMESTAMP`
- `GET /api.php?action=stats&start=TIMESTAMP&end=TIMESTAMP`
- `GET /api.php?action=hourly&start=TIMESTAMP&end=TIMESTAMP`
- `GET /api.php?action=anomalies&threshold=2.0&limit=100`
- `GET /api.php?action=status`
- `POST /api.php?action=annotate` (body: `{id, annotation}`)

## License

MIT License - see [LICENSE](LICENSE)

## Credits

Inspired by [BirdNET-Pi](https://github.com/Nachtzuster/BirdNET-Pi) for the dashboard design approach.

## Contributing

Contributions welcome! Please open an issue or pull request.

