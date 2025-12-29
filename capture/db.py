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
                
                -- Percentiles (dB) - estimated from samples
                l10_db REAL,
                l50_db REAL,
                l90_db REAL,
                
                -- Frequency band levels (dB)
                band_low_db REAL,
                band_mid_db REAL,
                band_high_db REAL,
                
                -- Other metrics
                silence_pct REAL,
                peak_freq_hz REAL,
                crest_factor REAL,
                dynamic_range REAL,
                
                -- Anomaly
                anomaly_score REAL DEFAULT 0,
                
                -- Annotation
                annotation TEXT,
                
                -- Sample info
                sample_seconds REAL,
                status TEXT DEFAULT 'ok',
                
                -- Spectrogram (compressed)
                spectrogram BLOB
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
                band_low_db, band_mid_db, band_high_db,
                silence_pct, peak_freq_hz, crest_factor, dynamic_range,
                anomaly_score, sample_seconds, status, spectrogram
            ) VALUES (
                :timestamp, :unix_time, :mean_db, :max_db, :min_db,
                :l10_db, :l50_db, :l90_db,
                :band_low_db, :band_mid_db, :band_high_db,
                :silence_pct, :peak_freq_hz, :crest_factor, :dynamic_range,
                :anomaly_score, :sample_seconds, :status, :spectrogram
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
        # Get current values
        row = conn.execute('''
            SELECT mean_db_avg, mean_db_std, samples
            FROM baseline
            WHERE day_of_week = ? AND hour = ?
        ''', (day_of_week, hour)).fetchone()
        
        if row is None:
            return
        
        avg, std, samples = row['mean_db_avg'], row['mean_db_std'], row['samples']
        
        # Exponential moving average (alpha = 0.1)
        alpha = 0.1
        if samples == 0:
            new_avg = mean_db
            new_std = std
        else:
            new_avg = avg * (1 - alpha) + mean_db * alpha
            # Update std only after enough samples
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

