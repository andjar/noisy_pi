"""
Database handling for Noisy Pi
"""
import sqlite3
import os
from contextlib import contextmanager
from . import config


def init_db():
    """Initialize the SQLite database."""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    
    with get_connection() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                unix_time INTEGER NOT NULL,
                
                -- Volume metrics (dB)
                mean_db REAL,
                max_db REAL,
                min_db REAL,
                
                -- Percentiles (dB)
                l10_db REAL,
                l50_db REAL,
                l90_db REAL,
                
                -- 7 primary frequency bands (dB) covering 0-24kHz
                band_0_200 REAL,      -- 0-200 Hz (sub-bass, bass)
                band_200_500 REAL,    -- 200-500 Hz (low-mid)
                band_500_1k REAL,     -- 500-1000 Hz (mid)
                band_1k_2k REAL,      -- 1-2 kHz (upper-mid)
                band_2k_4k REAL,      -- 2-4 kHz (presence)
                band_4k_8k REAL,      -- 4-8 kHz (brilliance)
                band_8k_24k REAL,     -- 8-24 kHz (air/ultrasonic)
                
                -- 8 additional frequency bands for detailed analysis
                band_0_100 REAL,      -- 0-100 Hz (infrasound/rumble)
                band_100_300 REAL,    -- 100-300 Hz (bass)
                band_300_800 REAL,    -- 300-800 Hz (low-mid detail)
                band_800_1500 REAL,   -- 800-1500 Hz (mid detail)
                band_1500_3k REAL,    -- 1500-3000 Hz (upper-mid detail)
                band_3k_6k REAL,      -- 3-6 kHz (presence detail)
                band_6k_12k REAL,     -- 6-12 kHz (brilliance detail)
                band_12k_24k REAL,    -- 12-24 kHz (ultrasonic)
                
                -- Spectral features
                spectral_centroid REAL,
                spectral_flatness REAL,
                dominant_freq REAL,
                
                -- Other metrics
                silence_pct REAL,
                dynamic_range REAL,
                
                -- Anomaly
                anomaly_score REAL DEFAULT 0,
                
                -- Annotation
                annotation TEXT,
                
                -- Sample info
                sample_seconds REAL,
                status TEXT DEFAULT 'ok',
                
                -- Spectrogram (compressed 8-bit, n_snapshots x n_bins)
                spectrogram BLOB,
                spectrogram_snapshots INTEGER DEFAULT 10,
                spectrogram_bins INTEGER DEFAULT 256
            );
            
            CREATE INDEX IF NOT EXISTS idx_timestamp ON measurements(timestamp);
            CREATE INDEX IF NOT EXISTS idx_unix_time ON measurements(unix_time);
            CREATE INDEX IF NOT EXISTS idx_anomaly ON measurements(anomaly_score);
            
            -- Baseline statistics for anomaly detection
            CREATE TABLE IF NOT EXISTS baseline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day_of_week INTEGER,
                hour INTEGER,
                mean_db_avg REAL,
                mean_db_std REAL,
                samples INTEGER DEFAULT 0,
                updated_at TEXT,
                UNIQUE(day_of_week, hour)
            );
            
            -- Anomaly snippets
            CREATE TABLE IF NOT EXISTS snippets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                measurement_id INTEGER,
                filename TEXT NOT NULL,
                anomaly_score REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (measurement_id) REFERENCES measurements(id)
            );
            
            PRAGMA journal_mode=WAL;
        ''')
        
        # Initialize baseline entries
        for dow in range(7):
            for hour in range(24):
                conn.execute('''
                    INSERT OR IGNORE INTO baseline (day_of_week, hour, mean_db_avg, mean_db_std, samples, updated_at)
                    VALUES (?, ?, -40.0, 10.0, 0, datetime('now'))
                ''', (dow, hour))
        
        conn.commit()


@contextmanager
def get_connection():
    """Get a database connection."""
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def store_measurement(data: dict) -> int:
    """Store a measurement in the database. Returns the row ID."""
    with get_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO measurements (
                timestamp, unix_time, mean_db, max_db, min_db,
                l10_db, l50_db, l90_db,
                band_0_200, band_200_500, band_500_1k, band_1k_2k,
                band_2k_4k, band_4k_8k, band_8k_24k,
                band_0_100, band_100_300, band_300_800, band_800_1500,
                band_1500_3k, band_3k_6k, band_6k_12k, band_12k_24k,
                spectral_centroid, spectral_flatness, dominant_freq,
                silence_pct, dynamic_range,
                anomaly_score, sample_seconds, status,
                spectrogram, spectrogram_snapshots, spectrogram_bins
            ) VALUES (
                :timestamp, :unix_time, :mean_db, :max_db, :min_db,
                :l10_db, :l50_db, :l90_db,
                :band_0_200, :band_200_500, :band_500_1k, :band_1k_2k,
                :band_2k_4k, :band_4k_8k, :band_8k_24k,
                :band_0_100, :band_100_300, :band_300_800, :band_800_1500,
                :band_1500_3k, :band_3k_6k, :band_6k_12k, :band_12k_24k,
                :spectral_centroid, :spectral_flatness, :dominant_freq,
                :silence_pct, :dynamic_range,
                :anomaly_score, :sample_seconds, :status,
                :spectrogram, :spectrogram_snapshots, :spectrogram_bins
            )
        ''', data)
        conn.commit()
        return cursor.lastrowid


def get_baseline(day_of_week: int, hour: int) -> tuple:
    """Get baseline statistics for anomaly detection."""
    with get_connection() as conn:
        row = conn.execute('''
            SELECT mean_db_avg, mean_db_std, samples
            FROM baseline
            WHERE day_of_week = ? AND hour = ?
        ''', (day_of_week, hour)).fetchone()
        
        if row:
            return row['mean_db_avg'], row['mean_db_std'], row['samples']
        return -40.0, 10.0, 0


def update_baseline(day_of_week: int, hour: int, mean_db: float):
    """Update baseline with exponential moving average."""
    if mean_db is None:
        return
    
    with get_connection() as conn:
        row = conn.execute('''
            SELECT mean_db_avg, mean_db_std, samples
            FROM baseline
            WHERE day_of_week = ? AND hour = ?
        ''', (day_of_week, hour)).fetchone()
        
        if row is None:
            return
        
        avg, std, samples = row['mean_db_avg'], row['mean_db_std'], row['samples']
        
        alpha = 0.1
        if samples == 0:
            new_avg = mean_db
            new_std = std
        else:
            new_avg = avg * (1 - alpha) + mean_db * alpha
            if samples >= 10:
                new_std = (std * std * (1 - alpha) + (mean_db - avg) ** 2 * alpha) ** 0.5
            else:
                new_std = std
        
        conn.execute('''
            UPDATE baseline
            SET mean_db_avg = ?, mean_db_std = ?, samples = samples + 1, updated_at = datetime('now')
            WHERE day_of_week = ? AND hour = ?
        ''', (new_avg, new_std, day_of_week, hour))
        conn.commit()


def store_snippet(timestamp: str, measurement_id: int, filename: str, anomaly_score: float):
    """Store snippet metadata."""
    with get_connection() as conn:
        conn.execute('''
            INSERT INTO snippets (timestamp, measurement_id, filename, anomaly_score)
            VALUES (?, ?, ?, ?)
        ''', (timestamp, measurement_id, filename, anomaly_score))
        conn.commit()


def get_recent_measurements(limit: int = 100):
    """Get recent measurements."""
    with get_connection() as conn:
        return conn.execute('''
            SELECT * FROM measurements
            ORDER BY unix_time DESC
            LIMIT ?
        ''', (limit,)).fetchall()
