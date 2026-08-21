import math
import random
import threading
import time
from datetime import datetime, timezone, timedelta

import db

DEFAULT_CONFIG = {
    "start_latitude": 31.2304,
    "start_longitude": 121.4737,
    "heading": 45.0,
    "speed": 12.0,
    "water_depth": 50.0,
    "depth_variation": 5.0,
    "wind_direction": 180.0,
    "wind_speed": 10.0,
    "wind_dir_variation": 30.0,
    "wind_speed_variation": 2.0,
    "temperature": 22.0,
    "humidity": 65.0,
    "temp_variation": 2.0,
    "humidity_variation": 5.0,
    "pressure": 1013.0,
    "ais_target_count": 5,
    "mmsi": 200123456,
    "satellites": 8,
    "hdop": 0.8,
    "altitude": 34.7,
    "water_speed": 0.0,
    "aton_target_count": 2,
    "ship_name": "SIM VESSEL",
    "callsign": "SIMCALL",
    "imo_number": 1234567,
    "ship_type_ais": 36,
    "destination": "SHANGHAI",
    "draught": 5.0,
    "vdo_msg_types": "1",
    "vdo_fragment_count": 1,
    "ais_pos_dev": 10.0,
    "ais_speed_dev": 0.1,
    "ais_heading_dev": 1.0,
    "radar_pos_dev": 30.0,
    "radar_bearing_dev": 1.5,
    "radar_speed_dev": 0.3,
    "radar_heading_dev": 2.0,
}


class ShipState:
    def __init__(self, config=None):
        self.utc_time = datetime.now(timezone.utc)
        self.latitude = DEFAULT_CONFIG["start_latitude"]
        self.longitude = DEFAULT_CONFIG["start_longitude"]
        self.heading = DEFAULT_CONFIG["heading"]
        self.speed = DEFAULT_CONFIG["speed"]
        self.water_depth = DEFAULT_CONFIG["water_depth"]
        self.wind_direction = DEFAULT_CONFIG["wind_direction"]
        self.wind_speed = DEFAULT_CONFIG["wind_speed"]
        self.temperature = DEFAULT_CONFIG["temperature"]
        self.humidity = DEFAULT_CONFIG["humidity"]
        self.pressure = DEFAULT_CONFIG["pressure"]
        self.mmsi = DEFAULT_CONFIG["mmsi"]
        self._extra = {}
        self.ais_targets = []
        self.aton_targets = []
        self.special_targets = []
        self.apply_config(config or {})

    def apply_config(self, cfg, reset_position=False):
        self._config = dict(DEFAULT_CONFIG)
        self._config.update(cfg)
        if reset_position or not getattr(self, "_initialized", False):
            self.latitude = self._config["start_latitude"]
            self.longitude = self._config["start_longitude"]
            self._initialized = True
        self.heading = self._config["heading"]
        self.speed = self._config["speed"]
        self.water_depth = self._config["water_depth"]
        self.wind_direction = self._config["wind_direction"]
        self.wind_speed = self._config["wind_speed"]
        self.temperature = self._config["temperature"]
        self.humidity = self._config["humidity"]
        self.pressure = self._config.get("pressure", 1013.0)
        self.mmsi = self._config.get("mmsi", 200123456)
        self.satellites = self._config.get("satellites", 8)
        self.hdop = self._config.get("hdop", 0.8)
        self.altitude = self._config.get("altitude", 34.7)
        self.water_speed = self._config.get("water_speed", 0.0) or self._config["speed"]
        self.aton_target_count = self._config.get("aton_target_count", 2)
        self.ship_name = self._config.get("ship_name", "SIM VESSEL")
        self.callsign = self._config.get("callsign", "SIMCALL")
        self.imo_number = self._config.get("imo_number", 1234567)
        self.ship_type_ais = self._config.get("ship_type_ais", 36)
        self.destination = self._config.get("destination", "SHANGHAI")
        self.draught = self._config.get("draught", 5.0)
        self.vdo_msg_types = self._config.get("vdo_msg_types", "1")
        self.vdo_fragment_count = self._config.get("vdo_fragment_count", 1)
        self.ais_pos_dev = self._config.get("ais_pos_dev", 10.0)
        self.ais_speed_dev = self._config.get("ais_speed_dev", 0.1)
        self.ais_heading_dev = self._config.get("ais_heading_dev", 1.0)
        self.radar_pos_dev = self._config.get("radar_pos_dev", 30.0)
        self.radar_bearing_dev = self._config.get("radar_bearing_dev", 1.5)
        self.radar_speed_dev = self._config.get("radar_speed_dev", 0.3)
        self.radar_heading_dev = self._config.get("radar_heading_dev", 2.0)
        self._load_targets()

    def get(self, key, default=None):
        if hasattr(self, key):
            return getattr(self, key)
        return self._extra.get(key, default)

    def _load_targets(self):
        start_lat = self._config.get("start_latitude", DEFAULT_CONFIG["start_latitude"])
        start_lon = self._config.get("start_longitude", DEFAULT_CONFIG["start_longitude"])
        cos_lat = max(math.cos(math.radians(start_lat)), 0.01)

        ais_db = db.load_ais_targets()
        self.ais_targets = []
        for t in ais_db:
            br = math.radians(t["bearing"])
            dist_nm = t["distance"]
            dlat = dist_nm * math.cos(br) / 60
            dlon = dist_nm * math.sin(br) / (60 * cos_lat)
            msg_types_str = t.get("msg_types", "1")
            msg_types_list = [int(x) for x in msg_types_str.split(",") if x.strip()]
            if not msg_types_list:
                msg_types_list = [1]
            self.ais_targets.append({
                "id": t["id"],
                "mmsi": t["mmsi"],
                "ship_name": t["ship_name"],
                "callsign": t["callsign"],
                "imo_number": t["imo_number"],
                "ship_type": t["ship_type"],
                "destination": t["destination"],
                "draught": t["draught"],
                "speed": t["speed"],
                "heading": t["heading"],
                "bearing": t["bearing"],
                "distance": t["distance"],
                "msg_types": msg_types_list,
                "fragment_count": t.get("fragment_count", 1),
                "latitude": start_lat + dlat,
                "longitude": start_lon + dlon,
                "cog": t["heading"],
            })

        aton_db = db.load_aton_targets()
        self.aton_targets = []
        for t in aton_db:
            br = math.radians(t["bearing"])
            dist_nm = t["distance"]
            dlat = dist_nm * math.cos(br) / 60
            dlon = dist_nm * math.sin(br) / (60 * cos_lat)
            msg_types_str = t.get("msg_types", "21")
            msg_types_list = [int(x) for x in msg_types_str.split(",") if x.strip()]
            if not msg_types_list:
                msg_types_list = [21]
            self.aton_targets.append({
                "id": t["id"],
                "mmsi": t["mmsi"],
                "name": t["name"],
                "aton_type": t["aton_type"],
                "bearing": t["bearing"],
                "distance": t["distance"],
                "msg_types": msg_types_list,
                "fragment_count": t.get("fragment_count", 1),
                "latitude": start_lat + dlat,
                "longitude": start_lon + dlon,
            })

        special_db = db.load_special_targets()
        self.special_targets = []
        for t in special_db:
            br = math.radians(t["bearing"])
            dist_nm = t["distance"]
            dlat = dist_nm * math.cos(br) / 60
            dlon = dist_nm * math.sin(br) / (60 * cos_lat)
            self.special_targets.append({
                "id": t["id"],
                "target_type": t["target_type"],
                "mmsi": t["mmsi"],
                "name": t["name"],
                "bearing": t["bearing"],
                "distance": t["distance"],
                "speed": t["speed"],
                "heading": t["heading"],
                "altitude": t["altitude"],
                "wind_speed": t["wind_speed"],
                "wind_direction": t["wind_direction"],
                "pressure": t["pressure"],
                "temperature": t["temperature"],
                "humidity": t["humidity"],
                "visibility": t["visibility"],
                "fragment_count": t["fragment_count"],
                "latitude": start_lat + dlat,
                "longitude": start_lon + dlon,
            })

    def refresh_targets(self):
        self._load_targets()

    def update(self, dt):
        self.utc_time = datetime.now(timezone.utc)
        self._update_position(dt)
        self._update_targets(dt)
        self._apply_variations()

    def _update_position(self, dt):
        dt_h = dt / 3600.0
        dist_deg = self.speed * dt_h / 60.0
        rad = math.radians(self.heading)
        self.latitude += dist_deg * math.cos(rad)
        lon_factor = 1.0 / max(math.cos(math.radians(self.latitude)), 0.01)
        self.longitude += dist_deg * math.sin(rad) * lon_factor
        if self.latitude > 89.9:
            self.latitude = 89.9
        elif self.latitude < -89.9:
            self.latitude = -89.9
        if self.longitude > 180:
            self.longitude -= 360
        elif self.longitude < -180:
            self.longitude += 360

    def _update_targets(self, dt):
        dt_h = dt / 3600.0
        for tgt in self.ais_targets:
            dist_deg = tgt["speed"] * dt_h / 60.0
            rad = math.radians(tgt["heading"])
            tgt["latitude"] += dist_deg * math.cos(rad)
            lon_factor = 1.0 / max(math.cos(math.radians(tgt["latitude"])), 0.01)
            tgt["longitude"] += dist_deg * math.sin(rad) * lon_factor
            tgt["cog"] = tgt["heading"] + random.uniform(-2, 2)
        for spec in self.special_targets:
            if spec.get("speed", 0) > 0:
                dist_deg = spec["speed"] * dt_h / 60.0
                rad = math.radians(spec["heading"])
                spec["latitude"] += dist_deg * math.cos(rad)
                lon_factor = 1.0 / max(math.cos(math.radians(spec["latitude"])), 0.01)
                spec["longitude"] += dist_deg * math.sin(rad) * lon_factor

    def _apply_variations(self):
        cfg = self._config
        self.water_depth += random.uniform(-1, 1) * cfg["depth_variation"] * 0.02
        self.water_depth = max(0.1, self.water_depth)
        self.wind_direction += random.uniform(-1, 1) * cfg["wind_dir_variation"] * 0.05
        self.wind_direction %= 360
        self.wind_speed += random.uniform(-1, 1) * cfg["wind_speed_variation"] * 0.02
        self.wind_speed = max(0, self.wind_speed)
        self.temperature += random.uniform(-1, 1) * cfg["temp_variation"] * 0.02
        self.humidity += random.uniform(-1, 1) * cfg["humidity_variation"] * 0.02
        self.humidity = max(0, min(100, self.humidity))
        self.pressure += random.uniform(-0.5, 0.5)
        self.pressure = max(950, min(1050, self.pressure))

    def to_dict(self):
        return {
            "running": False,
            "utc_time": self.utc_time.strftime("%Y-%m-%d %H:%M:%S"),
            "latitude": round(self.latitude, 6),
            "longitude": round(self.longitude, 6),
            "heading": round(self.heading, 1),
            "speed": round(self.speed, 1),
            "water_depth": round(self.water_depth, 1),
            "wind_direction": round(self.wind_direction, 1),
            "wind_speed": round(self.wind_speed, 1),
            "temperature": round(self.temperature, 1),
            "humidity": round(self.humidity, 1),
            "pressure": round(self.pressure, 1),
            "ais_target_count": len(self.ais_targets),
            "aton_target_count": len(self.aton_targets),
            "special_target_count": len(self.special_targets),
            "mmsi": self.mmsi,
            "config": self._config,
        }


class ShipSimulator:
    def __init__(self):
        self.state = ShipState()
        self.running = False
        self._thread = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()

    def start(self, config=None):
        with self._lock:
            if config:
                self.state.apply_config(config, reset_position=True)
            else:
                self.state.apply_config(self.state._config, reset_position=True)
            if self.running:
                return False
            self.running = True
            self._stop_evt.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            return True

    def stop(self):
        self._stop_evt.set()
        self.running = False
        return True

    def update_config(self, config):
        with self._lock:
            self.state.apply_config(config)

    def refresh_targets(self):
        with self._lock:
            self.state.refresh_targets()

    def get_state(self):
        with self._lock:
            d = self.state.to_dict()
            d["running"] = self.running
            return d

    def _run(self):
        last = time.time()
        while not self._stop_evt.is_set():
            now = time.time()
            dt = now - last
            last = now
            with self._lock:
                self.state.update(dt)
            self._stop_evt.wait(1.0)
