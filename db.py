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

_DB_PATH = os.environ.get("NMEA_DB_PATH", os.path.join(_APP_DIR, "nmea_sim.db"))

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

            CREATE TABLE IF NOT EXISTS ais_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mmsi INTEGER NOT NULL,
                ship_name TEXT DEFAULT '',
                callsign TEXT DEFAULT '',
                imo_number INTEGER DEFAULT 0,
                ship_type INTEGER DEFAULT 0,
                destination TEXT DEFAULT '',
                draught REAL DEFAULT 5.0,
                speed REAL DEFAULT 10.0,
                heading REAL DEFAULT 0.0,
                bearing REAL DEFAULT 0.0,
                distance REAL DEFAULT 3.0
            );

            CREATE TABLE IF NOT EXISTS aton_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mmsi INTEGER NOT NULL,
                name TEXT DEFAULT '',
                aton_type INTEGER DEFAULT 1,
                bearing REAL DEFAULT 0.0,
                distance REAL DEFAULT 2.0,
                msg_types TEXT DEFAULT '21',
                fragment_count INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS special_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_type TEXT NOT NULL,
                mmsi INTEGER NOT NULL,
                name TEXT DEFAULT '',
                bearing REAL DEFAULT 0.0,
                distance REAL DEFAULT 3.0,
                speed REAL DEFAULT 100.0,
                heading REAL DEFAULT 0.0,
                altitude REAL DEFAULT 1000.0,
                wind_speed REAL DEFAULT 15.0,
                wind_direction REAL DEFAULT 180.0,
                pressure REAL DEFAULT 1013.0,
                temperature REAL DEFAULT 22.0,
                humidity REAL DEFAULT 65.0,
                visibility REAL DEFAULT 10.0,
                fragment_count INTEGER DEFAULT 1
            );
        """)
        conn.execute("INSERT OR IGNORE INTO ship_config (id, updated_at) VALUES (1, ?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))

        for col, col_type, default in [
            ("satellites", "INTEGER", 8),
            ("hdop", "REAL", 0.8),
            ("altitude", "REAL", 34.7),
            ("water_speed", "REAL", 0.0),
            ("aton_target_count", "INTEGER", 2),
            ("ship_name", "TEXT", "'SIM VESSEL'"),
            ("callsign", "TEXT", "'SIMCALL'"),
            ("imo_number", "INTEGER", 1234567),
            ("ship_type_ais", "INTEGER", 36),
            ("destination", "TEXT", "'SHANGHAI'"),
            ("draught", "REAL", 5.0),
            ("vdo_msg_types", "TEXT", "'1'"),
            ("vdo_fragment_count", "INTEGER", 1),
            ("ais_pos_dev", "REAL", 10.0),
            ("ais_speed_dev", "REAL", 0.1),
            ("ais_heading_dev", "REAL", 1.0),
            ("radar_pos_dev", "REAL", 30.0),
            ("radar_bearing_dev", "REAL", 1.5),
            ("radar_speed_dev", "REAL", 0.3),
            ("radar_heading_dev", "REAL", 2.0),
        ]:
            try:
                conn.execute(f"ALTER TABLE ship_config ADD COLUMN {col} {col_type} DEFAULT {default}")
            except Exception:
                pass

        for col, col_type, default in [
            ("msg_types", "TEXT", "'1'"),
            ("fragment_count", "INTEGER", 1),
        ]:
            try:
                conn.execute(f"ALTER TABLE ais_targets ADD COLUMN {col} {col_type} DEFAULT {default}")
            except Exception:
                pass

        for col, col_type, default in [
            ("msg_types", "TEXT", "'21'"),
            ("fragment_count", "INTEGER", 1),
        ]:
            try:
                conn.execute(f"ALTER TABLE aton_targets ADD COLUMN {col} {col_type} DEFAULT {default}")
            except Exception:
                pass

        conn.commit()
        conn.close()
    _init_default_targets()


def _init_default_targets():
    with _lock:
        conn = _get_conn()
        count = conn.execute("SELECT COUNT(*) FROM ais_targets").fetchone()[0]
        if count == 0:
            defaults = [
                (201000001, "TARGET 01", "TGT0001", 1000001, 36, "SHANGHAI", 5.0, 10.0, 45.0, 30.0, 3.0, "1,5", 2),
                (412000001, "TARGET 02", "TGT0002", 2000002, 37, "TIANJIN", 6.5, 8.0, 90.0, 120.0, 5.0, "1,5", 2),
                (533000001, "TARGET 03", "TGT0003", 3000003, 52, "QINGDAO", 8.0, 15.0, 180.0, 240.0, 7.0, "1,5,24", 2),
            ]
            for d in defaults:
                conn.execute("INSERT INTO ais_targets (mmsi,ship_name,callsign,imo_number,ship_type,destination,draught,speed,heading,bearing,distance,msg_types,fragment_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", d)
        count = conn.execute("SELECT COUNT(*) FROM aton_targets").fetchone()[0]
        if count == 0:
            defaults = [
                (991234567, "LIGHTHOUSE A", 3, 60.0, 2.0, "21", 1),
                (992345678, "BUOY B", 1, 200.0, 4.0, "21", 1),
            ]
            for d in defaults:
                conn.execute("INSERT INTO aton_targets (mmsi,name,aton_type,bearing,distance,msg_types,fragment_count) VALUES (?,?,?,?,?,?,?)", d)
        count = conn.execute("SELECT COUNT(*) FROM special_targets").fetchone()[0]
        if count == 0:
            defaults = [
                ("weather", 970000001, "WEATHER STA", 90.0, 5.0, 0, 0, 0, 15.0, 180.0, 1013.0, 22.0, 65.0, 10.0, 2),
                ("aircraft", 970000002, "SAR AIRCRAFT", 180.0, 8.0, 150.0, 90.0, 2000.0, 0, 0, 0, 0, 0, 0, 1),
                ("basestation", 100000001, "BASE STATION", 0.0, 0.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1),
                ("sart", 970000003, "SART BEACON", 270.0, 3.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1),
                ("route", 970000004, "ROUTE BCAST", 45.0, 6.0, 12.0, 45.0, 0, 0, 0, 0, 0, 0, 0, 2),
            ]
            for d in defaults:
                conn.execute("INSERT INTO special_targets (target_type,mmsi,name,bearing,distance,speed,heading,altitude,wind_speed,wind_direction,pressure,temperature,humidity,visibility,fragment_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", d)
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
        "aton_target_count": int(row["aton_target_count"]),
        "ship_name": row["ship_name"],
        "callsign": row["callsign"],
        "imo_number": row["imo_number"],
        "ship_type_ais": row["ship_type_ais"],
        "destination": row["destination"],
        "draught": row["draught"],
        "vdo_msg_types": row["vdo_msg_types"] if "vdo_msg_types" in row.keys() else "1",
        "vdo_fragment_count": int(row["vdo_fragment_count"]) if "vdo_fragment_count" in row.keys() else 1,
        "ais_pos_dev": float(row["ais_pos_dev"]) if "ais_pos_dev" in row.keys() else 10.0,
        "ais_speed_dev": float(row["ais_speed_dev"]) if "ais_speed_dev" in row.keys() else 0.1,
        "ais_heading_dev": float(row["ais_heading_dev"]) if "ais_heading_dev" in row.keys() else 1.0,
        "radar_pos_dev": float(row["radar_pos_dev"]) if "radar_pos_dev" in row.keys() else 30.0,
        "radar_bearing_dev": float(row["radar_bearing_dev"]) if "radar_bearing_dev" in row.keys() else 1.5,
        "radar_speed_dev": float(row["radar_speed_dev"]) if "radar_speed_dev" in row.keys() else 0.3,
        "radar_heading_dev": float(row["radar_heading_dev"]) if "radar_heading_dev" in row.keys() else 2.0,
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
        "aton_target_count",
        "ship_name", "callsign", "imo_number", "ship_type_ais",
        "destination", "draught",
        "vdo_msg_types", "vdo_fragment_count",
        "ais_pos_dev", "ais_speed_dev", "ais_heading_dev",
        "radar_pos_dev", "radar_bearing_dev", "radar_speed_dev", "radar_heading_dev",
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


def load_ais_targets():
    with _lock:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM ais_targets ORDER BY id").fetchall()
        conn.close()
    return [{"id": r["id"], "mmsi": r["mmsi"], "ship_name": r["ship_name"],
             "callsign": r["callsign"], "imo_number": r["imo_number"],
             "ship_type": r["ship_type"], "destination": r["destination"],
             "draught": r["draught"], "speed": r["speed"], "heading": r["heading"],
             "bearing": r["bearing"], "distance": r["distance"],
             "msg_types": r["msg_types"] if "msg_types" in r.keys() else "1",
             "fragment_count": int(r["fragment_count"]) if "fragment_count" in r.keys() else 1} for r in rows]


def save_ais_target(data):
    with _lock:
        conn = _get_conn()
        conn.execute("""INSERT INTO ais_targets
            (mmsi,ship_name,callsign,imo_number,ship_type,destination,draught,speed,heading,bearing,distance,msg_types,fragment_count)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data["mmsi"],data["ship_name"],data["callsign"],data["imo_number"],
             data["ship_type"],data["destination"],data["draught"],
             data["speed"],data["heading"],data["bearing"],data["distance"],
             data.get("msg_types","1"),data.get("fragment_count",1)))
        conn.commit()
        conn.close()


def update_ais_target(target_id, data):
    with _lock:
        conn = _get_conn()
        conn.execute("""UPDATE ais_targets SET
            mmsi=?,ship_name=?,callsign=?,imo_number=?,ship_type=?,destination=?,
            draught=?,speed=?,heading=?,bearing=?,distance=?,msg_types=?,fragment_count=? WHERE id=?""",
            (data["mmsi"],data["ship_name"],data["callsign"],data["imo_number"],
             data["ship_type"],data["destination"],data["draught"],
             data["speed"],data["heading"],data["bearing"],data["distance"],
             data.get("msg_types","1"),data.get("fragment_count",1),target_id))
        conn.commit()
        conn.close()


def delete_ais_target(target_id):
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM ais_targets WHERE id=?", (target_id,))
        conn.commit()
        conn.close()


def load_aton_targets():
    with _lock:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM aton_targets ORDER BY id").fetchall()
        conn.close()
    return [{"id": r["id"], "mmsi": r["mmsi"], "name": r["name"],
             "aton_type": r["aton_type"], "bearing": r["bearing"],
             "distance": r["distance"],
             "msg_types": r["msg_types"] if "msg_types" in r.keys() else "21",
             "fragment_count": int(r["fragment_count"]) if "fragment_count" in r.keys() else 1} for r in rows]


def save_aton_target(data):
    with _lock:
        conn = _get_conn()
        conn.execute("INSERT INTO aton_targets (mmsi,name,aton_type,bearing,distance,msg_types,fragment_count) VALUES (?,?,?,?,?,?,?)",
            (data["mmsi"],data["name"],data["aton_type"],data["bearing"],data["distance"],
             data.get("msg_types","21"),data.get("fragment_count",1)))
        conn.commit()
        conn.close()


def update_aton_target(target_id, data):
    with _lock:
        conn = _get_conn()
        conn.execute("UPDATE aton_targets SET mmsi=?,name=?,aton_type=?,bearing=?,distance=?,msg_types=?,fragment_count=? WHERE id=?",
            (data["mmsi"],data["name"],data["aton_type"],data["bearing"],data["distance"],
             data.get("msg_types","21"),data.get("fragment_count",1),target_id))
        conn.commit()
        conn.close()


def delete_aton_target(target_id):
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM aton_targets WHERE id=?", (target_id,))
        conn.commit()
        conn.close()


def load_special_targets():
    with _lock:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM special_targets ORDER BY id").fetchall()
        conn.close()
    result = []
    for r in rows:
        result.append({
            "id": r["id"], "target_type": r["target_type"], "mmsi": r["mmsi"],
            "name": r["name"], "bearing": r["bearing"], "distance": r["distance"],
            "speed": r["speed"], "heading": r["heading"], "altitude": r["altitude"],
            "wind_speed": r["wind_speed"], "wind_direction": r["wind_direction"],
            "pressure": r["pressure"], "temperature": r["temperature"],
            "humidity": r["humidity"], "visibility": r["visibility"],
            "fragment_count": r["fragment_count"],
        })
    return result


def save_special_target(data):
    with _lock:
        conn = _get_conn()
        conn.execute("""INSERT INTO special_targets
            (target_type,mmsi,name,bearing,distance,speed,heading,altitude,
             wind_speed,wind_direction,pressure,temperature,humidity,visibility,fragment_count)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data["target_type"],data["mmsi"],data["name"],data["bearing"],data["distance"],
             data.get("speed",0),data.get("heading",0),data.get("altitude",0),
             data.get("wind_speed",0),data.get("wind_direction",0),
             data.get("pressure",0),data.get("temperature",0),
             data.get("humidity",0),data.get("visibility",0),
             data.get("fragment_count",1)))
        conn.commit()
        conn.close()


def update_special_target(target_id, data):
    with _lock:
        conn = _get_conn()
        conn.execute("""UPDATE special_targets SET
            target_type=?,mmsi=?,name=?,bearing=?,distance=?,speed=?,heading=?,altitude=?,
            wind_speed=?,wind_direction=?,pressure=?,temperature=?,humidity=?,visibility=?,fragment_count=?
            WHERE id=?""",
            (data["target_type"],data["mmsi"],data["name"],data["bearing"],data["distance"],
             data.get("speed",0),data.get("heading",0),data.get("altitude",0),
             data.get("wind_speed",0),data.get("wind_direction",0),
             data.get("pressure",0),data.get("temperature",0),
             data.get("humidity",0),data.get("visibility",0),
             data.get("fragment_count",1),target_id))
        conn.commit()
        conn.close()


def delete_special_target(target_id):
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM special_targets WHERE id=?", (target_id,))
        conn.commit()
        conn.close()
