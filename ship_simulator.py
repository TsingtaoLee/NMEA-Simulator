import math
import random
import threading
import time
from datetime import datetime, timezone, timedelta

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
        self._regen_targets()

    def get(self, key, default=None):
        if hasattr(self, key):
            return getattr(self, key)
        return self._extra.get(key, default)

    def _regen_targets(self):
        count = self._config.get("ais_target_count", 5)
        self.ais_targets = []
        for i in range(count):
            ang = random.uniform(0, 360)
            dist_nm = random.uniform(2, 15)
            dlat = dist_nm * math.cos(math.radians(ang)) / 60
            dlon = dist_nm * math.sin(math.radians(ang)) / (60 * math.cos(math.radians(self.latitude)))
            tgt_lat = self.latitude + dlat
            tgt_lon = self.longitude + dlon
            mmsi = random.randint(200000000, 775999999)
            tgt_heading = random.uniform(0, 360)
            tgt_speed = random.uniform(5, 18)
            self.ais_targets.append({
                "mmsi": mmsi,
                "latitude": tgt_lat,
                "longitude": tgt_lon,
                "heading": tgt_heading,
                "cog": tgt_heading + random.uniform(-10, 10),
                "speed": tgt_speed,
            })

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
