"""
SQLite database interface for Noisy Pi.
"""
import sqlite3
import zlib
import struct
import time
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

from config import DB_PATH, DATA_DIR


def ensure_data_dir():
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection():
    """Get a database connection with WAL mode enabled."""
    ensure_data_dir()
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """Initialize the database schema."""
    with get_connection() as conn:
        # Main measurements table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY,
                timestamp INTEGER NOT NULL,
                
                -- Aggregated metrics (dB)
                laeq REAL,
                lmax REAL,
                lmin REAL,
                l10 REAL,
                l50 REAL,
                l90 REAL,
                
                -- Spectral shape descriptors
                spectral_centroid REAL,
                spectral_flatness REAL,
                dominant_freq INTEGER,
                
                -- Event detection
                event_count INTEGER,
                
                -- Full spectrogram data (256 bins x 10 snapshots, compressed)
                spectrogram BLOB,
                
                -- Anomaly detection
                anomaly_score REAL,
                
                -- Manual annotation
                annotation TEXT,
                
                -- Audio snippet path (if saved)
                snippet_path TEXT,
                
                UNIQUE(timestamp)
            )
        """)
        
        # Indexes for common queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_measurements_timestamp 
            ON measurements(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_measurements_anomaly 
            ON measurements(anomaly_score) WHERE anomaly_score > 2.0
        """)
        
        # Baseline model table (hourly patterns per day-of-week)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS baseline (
                day_of_week INTEGER,
                hour INTEGER,
                laeq_mean REAL,
                laeq_std REAL,
                spectral_mean BLOB,
                sample_count INTEGER,
                updated_at INTEGER,
                PRIMARY KEY (day_of_week, hour)
            )
        """)
        
        # Settings table for runtime configuration
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # Processed files tracking (for file-watching mode)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_files (
                filename TEXT PRIMARY KEY,
                processed_at INTEGER,
                file_size INTEGER,
                measurement_id INTEGER,
                FOREIGN KEY (measurement_id) REFERENCES measurements(id)
            )
        """)
        
        # Index for cleanup of old entries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_processed_files_time 
            ON processed_files(processed_at)
        """)
        
        conn.commit()
        print(f"Database initialized at {DB_PATH}")


def compress_spectrogram(data: bytes) -> bytes:
    """Compress spectrogram data using zlib."""
    return zlib.compress(data, level=6)


def decompress_spectrogram(data: bytes) -> bytes:
    """Decompress spectrogram data."""
    return zlib.decompress(data)


def insert_measurement(
    timestamp: int,
    laeq: float,
    lmax: float,
    lmin: float,
    l10: float,
    l50: float,
    l90: float,
    spectral_centroid: float,
    spectral_flatness: float,
    dominant_freq: int,
    event_count: int,
    spectrogram: bytes,
    anomaly_score: float = None,
    snippet_path: str = None
) -> int:
    """Insert a measurement into the database."""
    compressed = compress_spectrogram(spectrogram)
    
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT OR REPLACE INTO measurements (
                timestamp, laeq, lmax, lmin, l10, l50, l90,
                spectral_centroid, spectral_flatness, dominant_freq,
                event_count, spectrogram, anomaly_score, snippet_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, laeq, lmax, lmin, l10, l50, l90,
            spectral_centroid, spectral_flatness, dominant_freq,
            event_count, compressed, anomaly_score, snippet_path
        ))
        conn.commit()
        return cursor.lastrowid


def get_measurements(
    start_time: int,
    end_time: int,
    include_spectrogram: bool = False
) -> List[Dict[str, Any]]:
    """Get measurements within a time range."""
    columns = [
        "id", "timestamp", "laeq", "lmax", "lmin", "l10", "l50", "l90",
        "spectral_centroid", "spectral_flatness", "dominant_freq",
        "event_count", "anomaly_score", "annotation"
    ]
    if include_spectrogram:
        columns.append("spectrogram")
    
    with get_connection() as conn:
        cursor = conn.execute(f"""
            SELECT {', '.join(columns)}
            FROM measurements
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        results = []
        for row in cursor:
            item = dict(row)
            if include_spectrogram and item.get("spectrogram"):
                item["spectrogram"] = decompress_spectrogram(item["spectrogram"])
            results.append(item)
        return results


def get_measurement_by_id(measurement_id: int) -> Optional[Dict[str, Any]]:
    """Get a single measurement by ID."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT * FROM measurements WHERE id = ?
        """, (measurement_id,))
        row = cursor.fetchone()
        if row:
            item = dict(row)
            if item.get("spectrogram"):
                item["spectrogram"] = decompress_spectrogram(item["spectrogram"])
            return item
        return None


def update_annotation(measurement_id: int, annotation: str) -> bool:
    """Update the annotation for a measurement."""
    with get_connection() as conn:
        cursor = conn.execute("""
            UPDATE measurements SET annotation = ? WHERE id = ?
        """, (annotation, measurement_id))
        conn.commit()
        return cursor.rowcount > 0


def get_snippet_path(measurement_id: int) -> Optional[str]:
    """Get the snippet path for a measurement."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT snippet_path FROM measurements WHERE id = ?
        """, (measurement_id,))
        row = cursor.fetchone()
        return row['snippet_path'] if row else None


def delete_snippet(measurement_id: int) -> bool:
    """Remove snippet path from a measurement (file deletion handled separately)."""
    with get_connection() as conn:
        cursor = conn.execute("""
            UPDATE measurements SET snippet_path = NULL WHERE id = ?
        """, (measurement_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_snippets_list(limit: int = 100) -> List[Dict[str, Any]]:
    """Get list of measurements that have snippets."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT id, timestamp, laeq, anomaly_score, annotation, snippet_path
            FROM measurements
            WHERE snippet_path IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor]


def get_anomalies(
    start_time: int = None,
    end_time: int = None,
    threshold: float = 2.0,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get measurements with anomaly scores above threshold."""
    query = """
        SELECT id, timestamp, laeq, anomaly_score, annotation
        FROM measurements
        WHERE anomaly_score > ?
    """
    params = [threshold]
    
    if start_time:
        query += " AND timestamp >= ?"
        params.append(start_time)
    if end_time:
        query += " AND timestamp <= ?"
        params.append(end_time)
    
    query += " ORDER BY anomaly_score DESC LIMIT ?"
    params.append(limit)
    
    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor]


def get_baseline(day_of_week: int, hour: int) -> Optional[Dict[str, Any]]:
    """Get baseline data for a specific day/hour combination."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT * FROM baseline WHERE day_of_week = ? AND hour = ?
        """, (day_of_week, hour))
        row = cursor.fetchone()
        if row:
            item = dict(row)
            if item.get("spectral_mean"):
                item["spectral_mean"] = decompress_spectrogram(item["spectral_mean"])
            return item
        return None


def update_baseline(
    day_of_week: int,
    hour: int,
    laeq_mean: float,
    laeq_std: float,
    spectral_mean: bytes,
    sample_count: int
):
    """Update or insert baseline data."""
    compressed = compress_spectrogram(spectral_mean)
    
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO baseline (
                day_of_week, hour, laeq_mean, laeq_std,
                spectral_mean, sample_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            day_of_week, hour, laeq_mean, laeq_std,
            compressed, sample_count, int(time.time())
        ))
        conn.commit()


def get_stats(start_time: int, end_time: int) -> Dict[str, Any]:
    """Get aggregate statistics for a time range."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as count,
                AVG(laeq) as avg_laeq,
                MAX(lmax) as max_level,
                MIN(lmin) as min_level,
                AVG(spectral_centroid) as avg_centroid,
                SUM(CASE WHEN anomaly_score > 2.0 THEN 1 ELSE 0 END) as anomaly_count
            FROM measurements
            WHERE timestamp >= ? AND timestamp <= ?
        """, (start_time, end_time))
        return dict(cursor.fetchone())


def get_hourly_stats(start_time: int, end_time: int) -> List[Dict[str, Any]]:
    """Get hourly aggregated statistics."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT 
                (timestamp / 3600) * 3600 as hour_start,
                COUNT(*) as count,
                AVG(laeq) as avg_laeq,
                MAX(lmax) as max_level,
                MIN(lmin) as min_level,
                AVG(l50) as avg_l50,
                SUM(CASE WHEN anomaly_score > 2.0 THEN 1 ELSE 0 END) as anomaly_count
            FROM measurements
            WHERE timestamp >= ? AND timestamp <= ?
            GROUP BY hour_start
            ORDER BY hour_start
        """, (start_time, end_time))
        return [dict(row) for row in cursor]


def is_file_processed(filename: str) -> bool:
    """Check if a file has already been processed."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT 1 FROM processed_files WHERE filename = ?
        """, (filename,))
        return cursor.fetchone() is not None


def mark_file_processed(filename: str, file_size: int, measurement_id: int = None):
    """Mark a file as processed."""
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO processed_files 
            (filename, processed_at, file_size, measurement_id)
            VALUES (?, ?, ?, ?)
        """, (filename, int(time.time()), file_size, measurement_id))
        conn.commit()


def cleanup_old_processed_files(days: int = 7):
    """Remove entries older than N days to keep the table small."""
    cutoff = int(time.time()) - (days * 86400)
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM processed_files WHERE processed_at < ?
        """, (cutoff,))
        conn.commit()


def get_processed_file_count() -> int:
    """Get count of processed files (for stats)."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM processed_files")
        return cursor.fetchone()[0]


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        init_database()
    else:
        print("Usage: python db.py --init")

