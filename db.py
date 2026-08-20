import json
import os
import sqlite3
import sys
import threading
from datetime import datetime

if getattr(sys, 'frozen', False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))

_DB_PATH = os.path.join(_APP_DIR, "nmea_sim.db")

_lock = threading.Lock()


def _get_conn():
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _lock:
        conn = _get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ship_config (
                id INTEGER PRIMARY KEY DEFAULT 1,
                start_latitude REAL DEFAULT 31.2304,
                start_longitude REAL DEFAULT 121.4737,
                heading REAL DEFAULT 45.0,
                speed REAL DEFAULT 12.0,
                water_depth REAL DEFAULT 50.0,
                depth_variation REAL DEFAULT 5.0,
                wind_direction REAL DEFAULT 180.0,
                wind_speed REAL DEFAULT 10.0,
                wind_dir_variation REAL DEFAULT 30.0,
                wind_speed_variation REAL DEFAULT 2.0,
                temperature REAL DEFAULT 22.0,
                humidity REAL DEFAULT 65.0,
                temp_variation REAL DEFAULT 2.0,
                humidity_variation REAL DEFAULT 5.0,
                pressure REAL DEFAULT 1013.0,
                ais_target_count INTEGER DEFAULT 5,
                mmsi INTEGER DEFAULT 200123456,
                running INTEGER DEFAULT 0,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS interfaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                protocol TEXT NOT NULL,
                ip TEXT NOT NULL,
                port INTEGER NOT NULL,
                formats TEXT NOT NULL,
                auto_connect INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            );
        """)
        conn.execute("INSERT OR IGNORE INTO ship_config (id, updated_at) VALUES (1, ?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))

        for col, col_type, default in [
            ("satellites", "INTEGER", 8),
            ("hdop", "REAL", 0.8),
            ("altitude", "REAL", 34.7),
            ("water_speed", "REAL", 0.0),
        ]:
            try:
                conn.execute(f"ALTER TABLE ship_config ADD COLUMN {col} {col_type} DEFAULT {default}")
            except Exception:
                pass

        conn.commit()
        conn.close()


def load_ship_config():
    with _lock:
        conn = _get_conn()
        row = conn.execute("SELECT * FROM ship_config WHERE id=1").fetchone()
        conn.close()
    if not row:
        return {}
    return {
        "start_latitude": row["start_latitude"],
        "start_longitude": row["start_longitude"],
        "heading": row["heading"],
        "speed": row["speed"],
        "water_depth": row["water_depth"],
        "depth_variation": row["depth_variation"],
        "wind_direction": row["wind_direction"],
        "wind_speed": row["wind_speed"],
        "wind_dir_variation": row["wind_dir_variation"],
        "wind_speed_variation": row["wind_speed_variation"],
        "temperature": row["temperature"],
        "humidity": row["humidity"],
        "temp_variation": row["temp_variation"],
        "humidity_variation": row["humidity_variation"],
        "pressure": row["pressure"],
        "ais_target_count": row["ais_target_count"],
        "mmsi": row["mmsi"],
        "satellites": row["satellites"],
        "hdop": row["hdop"],
        "altitude": row["altitude"],
        "water_speed": row["water_speed"],
        "running": bool(row["running"]),
    }


def save_ship_config(config):
    keys = [
        "start_latitude", "start_longitude", "heading", "speed",
        "water_depth", "depth_variation", "wind_direction", "wind_speed",
        "wind_dir_variation", "wind_speed_variation", "temperature",
        "humidity", "temp_variation", "humidity_variation", "pressure",
        "ais_target_count", "mmsi", "satellites", "hdop", "altitude",
        "water_speed",
    ]
    values = [config.get(k) for k in keys]
    running = 1 if config.get("running") else 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join([f"{k}=?" for k in keys])
    params = values + [running, now]
    with _lock:
        conn = _get_conn()
        conn.execute(f"UPDATE ship_config SET {set_clause}, running=?, updated_at=? WHERE id=1", params)
        conn.commit()
        conn.close()


def save_ship_running(running):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _lock:
        conn = _get_conn()
        conn.execute("UPDATE ship_config SET running=?, updated_at=? WHERE id=1", (1 if running else 0, now))
        conn.commit()
        conn.close()


def load_interfaces():
    with _lock:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM interfaces ORDER BY created_at").fetchall()
        conn.close()
    result = []
    for row in rows:
        result.append({
            "id": row["id"],
            "name": row["name"],
            "protocol": row["protocol"],
            "ip": row["ip"],
            "port": row["port"],
            "formats": json.loads(row["formats"]),
            "auto_connect": bool(row["auto_connect"]),
            "created_at": row["created_at"],
        })
    return result


def save_interface(iface_id, name, protocol, ip, port, formats, auto_connect=True, created_at=None):
    if created_at is None:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formats_json = json.dumps(formats)
    with _lock:
        conn = _get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO interfaces (id, name, protocol, ip, port, formats, auto_connect, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (iface_id, name, protocol, ip, port, formats_json, 1 if auto_connect else 0, created_at))
        conn.commit()
        conn.close()


def delete_interface(iface_id):
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM interfaces WHERE id=?", (iface_id,))
        conn.commit()
        conn.close()
