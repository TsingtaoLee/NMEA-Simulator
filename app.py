import os
import re
import sys
import threading
import socket as _socket
import webbrowser
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO

from ship_simulator import ShipSimulator, DEFAULT_CONFIG
from nmea_generator import NMEAGenerator, NMEA_FORMATS, FORMAT_CODES
from interface_manager import InterfaceManager
import db

if getattr(sys, 'frozen', False):
    _BUNDLE_DIR = sys._MEIPASS
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    _APP_DIR = _BUNDLE_DIR

app = Flask(__name__,
            static_folder=os.path.join(_BUNDLE_DIR, "static"),
            template_folder=os.path.join(_BUNDLE_DIR, "templates"))
app.config["SECRET_KEY"] = "nmea-sim-2026"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

db.init_db()

ship_sim = ShipSimulator()
nmea_gen = NMEAGenerator()

saved_config = db.load_ship_config()
if saved_config:
    ship_sim.state.apply_config(saved_config)
    if saved_config.get("running"):
        ship_sim.start(saved_config)

_log_buffer = []
_MAX_LOGS = 500


def log_callback(interface_id, interface_name, level, message, nmea_raw=None):
    entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "level": level,
        "message": message,
        "interface_id": interface_id,
        "interface_name": interface_name,
        "nmea_raw": nmea_raw,
    }
    _log_buffer.append(entry)
    if len(_log_buffer) > _MAX_LOGS:
        del _log_buffer[: len(_log_buffer) - _MAX_LOGS]
    socketio.emit("log", entry)


iface_mgr = InterfaceManager(ship_sim, nmea_gen, log_callback)

for saved_iface in db.load_interfaces():
    iface_mgr.create(
        name=saved_iface["name"],
        protocol=saved_iface["protocol"],
        ip=saved_iface["ip"],
        port=saved_iface["port"],
        formats=saved_iface["formats"],
        auto_connect=saved_iface.get("auto_connect", True),
        iface_id=saved_iface["id"],
        created_at=saved_iface["created_at"],
    )

_IP_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$"
)


def get_local_ips():
    """获取本机所有网卡 IPv4 地址"""
    ips = ["0.0.0.0"]
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and ip not in ips:
            ips.append(ip)
    except Exception:
        pass
    try:
        hostname = _socket.gethostname()
        for info in _socket.getaddrinfo(hostname, None, _socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("169.254") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips


def _validate_iface(data, is_create=True, exclude_id=None):
    errors = []
    name = (data.get("name") or "").strip()
    if not name:
        errors.append("接口名称不能为空")
    elif len(name) > 32:
        errors.append("接口名称最长32字符")

    protocol = data.get("protocol", "TCP").upper()
    if protocol not in ("TCP", "UDP"):
        errors.append("协议必须为 TCP 或 UDP")

    ip = (data.get("ip") or "").strip()
    if not ip:
        errors.append("IP地址不能为空")
    elif not _IP_RE.match(ip):
        errors.append("IP地址格式无效")
    else:
        try:
            _socket.inet_aton(ip)
        except OSError:
            errors.append("IP地址无效")

    try:
        port = int(data.get("port", 0))
        if port < 1 or port > 65535:
            errors.append("端口范围 1-65535")
    except (ValueError, TypeError):
        errors.append("端口必须为数字")
        port = 0

    formats = data.get("formats", [])
    if not isinstance(formats, list) or len(formats) == 0:
        errors.append("至少选择一种数据格式")
    else:
        for f in formats:
            if f not in FORMAT_CODES:
                errors.append(f"未知格式: {f}")
                break

    if port and protocol in ("TCP", "UDP") and not errors:
        if port == 8972:
            errors.append("端口 8972 被系统占用，请使用其他端口")
        else:
            for iface in iface_mgr.list():
                if exclude_id and iface["id"] == exclude_id:
                    continue
                if iface["port"] == port and iface["protocol"] == protocol:
                    errors.append(f"端口 {port} 已被接口「{iface['name']}」({iface['protocol']}) 占用")
                    break

    return {
        "name": name,
        "protocol": protocol,
        "ip": ip,
        "port": port,
        "formats": formats,
    }, errors


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/ship/state")
def api_ship_state():
    return jsonify(ship_sim.get_state())


@app.route("/api/ship/defaults")
def api_ship_defaults():
    return jsonify(DEFAULT_CONFIG)


@app.route("/api/ship/start", methods=["POST"])
def api_ship_start():
    config = request.json or {}
    merged = dict(DEFAULT_CONFIG)
    merged.update(db.load_ship_config())
    merged.update(config)
    db.save_ship_config(merged)
    ok = ship_sim.start(merged)
    db.save_ship_running(True)
    state = ship_sim.get_state()
    socketio.emit("ship_update", state)
    return jsonify({"ok": ok, "state": state})


@app.route("/api/ship/stop", methods=["POST"])
def api_ship_stop():
    ship_sim.stop()
    db.save_ship_running(False)
    state = ship_sim.get_state()
    socketio.emit("ship_update", state)
    return jsonify({"ok": True, "state": state})


@app.route("/api/ship/config", methods=["POST"])
def api_ship_config():
    config = request.json or {}
    merged = dict(DEFAULT_CONFIG)
    merged.update(db.load_ship_config())
    merged.update(config)
    db.save_ship_config(merged)
    ship_sim.update_config(merged)
    state = ship_sim.get_state()
    socketio.emit("ship_update", state)
    return jsonify({"ok": True, "state": state})


@app.route("/api/ship/saved-config")
def api_ship_saved_config():
    return jsonify(db.load_ship_config())


@app.route("/api/nmea-formats")
def api_formats():
    return jsonify(NMEA_FORMATS)


# ---- AIS Target Management ----

@app.route("/api/targets/ais")
def api_list_ais_targets():
    return jsonify(db.load_ais_targets())


@app.route("/api/targets/ais", methods=["POST"])
def api_create_ais_target():
    data = request.json or {}
    required = ["mmsi", "ship_name", "callsign", "imo_number", "ship_type",
                "destination", "draught", "speed", "heading", "bearing", "distance"]
    errors = []
    for f in required:
        if f not in data or data[f] is None:
            errors.append(f"缺少字段: {f}")
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    try:
        data["mmsi"] = int(data["mmsi"])
        data["imo_number"] = int(data["imo_number"])
        data["ship_type"] = int(data["ship_type"])
        data["draught"] = float(data["draught"])
        data["speed"] = float(data["speed"])
        data["heading"] = float(data["heading"]) % 360
        data["bearing"] = float(data["bearing"]) % 360
        data["distance"] = float(data["distance"])
        data["msg_types"] = data.get("msg_types", "1")
        data["fragment_count"] = int(data.get("fragment_count", 1))
    except (ValueError, TypeError) as e:
        return jsonify({"ok": False, "errors": [f"数据类型错误: {e}"]}), 400
    db.save_ais_target(data)
    ship_sim.refresh_targets()
    return jsonify({"ok": True, "data": data})


@app.route("/api/targets/ais/<int:target_id>", methods=["PUT"])
def api_update_ais_target(target_id):
    data = request.json or {}
    try:
        data["mmsi"] = int(data["mmsi"])
        data["imo_number"] = int(data["imo_number"])
        data["ship_type"] = int(data["ship_type"])
        data["draught"] = float(data["draught"])
        data["speed"] = float(data["speed"])
        data["heading"] = float(data["heading"]) % 360
        data["bearing"] = float(data["bearing"]) % 360
        data["distance"] = float(data["distance"])
        data["msg_types"] = data.get("msg_types", "1")
        data["fragment_count"] = int(data.get("fragment_count", 1))
    except (ValueError, TypeError, KeyError) as e:
        return jsonify({"ok": False, "errors": [f"数据类型错误: {e}"]}), 400
    db.update_ais_target(target_id, data)
    ship_sim.refresh_targets()
    return jsonify({"ok": True, "data": data})


@app.route("/api/targets/ais/<int:target_id>", methods=["DELETE"])
def api_delete_ais_target(target_id):
    db.delete_ais_target(target_id)
    ship_sim.refresh_targets()
    return jsonify({"ok": True})


# ---- ATON Target Management ----

@app.route("/api/targets/aton")
def api_list_aton_targets():
    return jsonify(db.load_aton_targets())


@app.route("/api/targets/aton", methods=["POST"])
def api_create_aton_target():
    data = request.json or {}
    required = ["mmsi", "name", "aton_type", "bearing", "distance"]
    errors = []
    for f in required:
        if f not in data or data[f] is None:
            errors.append(f"缺少字段: {f}")
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    try:
        data["mmsi"] = int(data["mmsi"])
        data["aton_type"] = int(data["aton_type"])
        data["bearing"] = float(data["bearing"]) % 360
        data["distance"] = float(data["distance"])
        data["msg_types"] = data.get("msg_types", "21")
        data["fragment_count"] = int(data.get("fragment_count", 1))
    except (ValueError, TypeError) as e:
        return jsonify({"ok": False, "errors": [f"数据类型错误: {e}"]}), 400
    db.save_aton_target(data)
    ship_sim.refresh_targets()
    return jsonify({"ok": True, "data": data})


@app.route("/api/targets/aton/<int:target_id>", methods=["PUT"])
def api_update_aton_target(target_id):
    data = request.json or {}
    try:
        data["mmsi"] = int(data["mmsi"])
        data["aton_type"] = int(data["aton_type"])
        data["bearing"] = float(data["bearing"]) % 360
        data["distance"] = float(data["distance"])
        data["msg_types"] = data.get("msg_types", "21")
        data["fragment_count"] = int(data.get("fragment_count", 1))
    except (ValueError, TypeError, KeyError) as e:
        return jsonify({"ok": False, "errors": [f"数据类型错误: {e}"]}), 400
    db.update_aton_target(target_id, data)
    ship_sim.refresh_targets()
    return jsonify({"ok": True, "data": data})


@app.route("/api/targets/aton/<int:target_id>", methods=["DELETE"])
def api_delete_aton_target(target_id):
    db.delete_aton_target(target_id)
    ship_sim.refresh_targets()
    return jsonify({"ok": True})


# ---- Special Target Management ----

SPECIAL_TARGET_TYPES = ["weather", "aircraft", "basestation", "sart", "route"]


@app.route("/api/targets/special")
def api_list_special_targets():
    return jsonify(db.load_special_targets())


@app.route("/api/targets/special", methods=["POST"])
def api_create_special_target():
    data = request.json or {}
    required = ["target_type", "mmsi", "name", "bearing", "distance"]
    errors = []
    for f in required:
        if f not in data or data[f] is None:
            errors.append(f"缺少字段: {f}")
    if data.get("target_type") and data["target_type"] not in SPECIAL_TARGET_TYPES:
        errors.append(f"目标类型必须是: {', '.join(SPECIAL_TARGET_TYPES)}")
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    try:
        data["mmsi"] = int(data["mmsi"])
        data["bearing"] = float(data["bearing"]) % 360
        data["distance"] = float(data["distance"])
        data["speed"] = float(data.get("speed", 0))
        data["heading"] = float(data.get("heading", 0)) % 360
        data["altitude"] = float(data.get("altitude", 0))
        data["wind_speed"] = float(data.get("wind_speed", 0))
        data["wind_direction"] = float(data.get("wind_direction", 0)) % 360
        data["pressure"] = float(data.get("pressure", 0))
        data["temperature"] = float(data.get("temperature", 0))
        data["humidity"] = float(data.get("humidity", 0))
        data["visibility"] = float(data.get("visibility", 0))
        data["fragment_count"] = int(data.get("fragment_count", 1))
    except (ValueError, TypeError) as e:
        return jsonify({"ok": False, "errors": [f"数据类型错误: {e}"]}), 400
    db.save_special_target(data)
    ship_sim.refresh_targets()
    return jsonify({"ok": True, "data": data})


@app.route("/api/targets/special/<int:target_id>", methods=["PUT"])
def api_update_special_target(target_id):
    data = request.json or {}
    try:
        data["mmsi"] = int(data["mmsi"])
        data["bearing"] = float(data["bearing"]) % 360
        data["distance"] = float(data["distance"])
        data["speed"] = float(data.get("speed", 0))
        data["heading"] = float(data.get("heading", 0)) % 360
        data["altitude"] = float(data.get("altitude", 0))
        data["wind_speed"] = float(data.get("wind_speed", 0))
        data["wind_direction"] = float(data.get("wind_direction", 0)) % 360
        data["pressure"] = float(data.get("pressure", 0))
        data["temperature"] = float(data.get("temperature", 0))
        data["humidity"] = float(data.get("humidity", 0))
        data["visibility"] = float(data.get("visibility", 0))
        data["fragment_count"] = int(data.get("fragment_count", 1))
    except (ValueError, TypeError, KeyError) as e:
        return jsonify({"ok": False, "errors": [f"数据类型错误: {e}"]}), 400
    db.update_special_target(target_id, data)
    ship_sim.refresh_targets()
    return jsonify({"ok": True, "data": data})


@app.route("/api/targets/special/<int:target_id>", methods=["DELETE"])
def api_delete_special_target(target_id):
    db.delete_special_target(target_id)
    ship_sim.refresh_targets()
    return jsonify({"ok": True})


@app.route("/api/local-ips")
def api_local_ips():
    return jsonify(get_local_ips())


@app.route("/api/interfaces")
def api_list_interfaces():
    return jsonify(iface_mgr.list())


@app.route("/api/interfaces", methods=["POST"])
def api_create_interface():
    data = request.json or {}
    validated, errors = _validate_iface(data)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    auto = data.get("auto_connect", True)
    iface = iface_mgr.create(
        name=validated["name"],
        protocol=validated["protocol"],
        ip=validated["ip"],
        port=validated["port"],
        formats=validated["formats"],
        auto_connect=auto,
    )
    db.save_interface(iface.id, iface.name, iface.protocol, iface.ip, iface.port, iface.formats, auto, iface.created_at)
    socketio.emit("interface_update", {"action": "create", "data": iface.to_dict()})
    return jsonify({"ok": True, "data": iface.to_dict()})


@app.route("/api/interfaces/<iface_id>")
def api_get_interface(iface_id):
    iface = iface_mgr.get(iface_id)
    if not iface:
        return jsonify({"ok": False, "error": "接口不存在"}), 404
    return jsonify({"ok": True, "data": iface.to_dict()})


@app.route("/api/interfaces/<iface_id>", methods=["PUT"])
def api_update_interface(iface_id):
    iface = iface_mgr.get(iface_id)
    if not iface:
        return jsonify({"ok": False, "error": "接口不存在"}), 404
    data = request.json or {}
    validated, errors = _validate_iface(data, exclude_id=iface_id)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    result = iface_mgr.update(
        iface_id,
        validated["name"],
        validated["protocol"],
        validated["ip"],
        validated["port"],
        validated["formats"],
    )
    db.save_interface(result["id"], result["name"], result["protocol"], result["ip"], result["port"], result["formats"], True, result["created_at"])
    socketio.emit("interface_update", {"action": "update", "data": result})
    return jsonify({"ok": True, "data": result})


@app.route("/api/interfaces/<iface_id>", methods=["DELETE"])
def api_delete_interface(iface_id):
    if iface_mgr.delete(iface_id):
        db.delete_interface(iface_id)
        socketio.emit("interface_update", {"action": "delete", "data": {"id": iface_id}})
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "接口不存在"}), 404


@app.route("/api/interfaces/<iface_id>/connect", methods=["POST"])
def api_connect_interface(iface_id):
    if iface_mgr.connect(iface_id):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "连接失败，接口可能已在运行"}), 400


@app.route("/api/interfaces/<iface_id>/disconnect", methods=["POST"])
def api_disconnect_interface(iface_id):
    iface_mgr.disconnect(iface_id)
    return jsonify({"ok": True})


@app.route("/api/logs")
def api_logs():
    return jsonify({"logs": _log_buffer[-200:]})


@socketio.on("connect")
def on_connect():
    socketio.emit("ship_update", ship_sim.get_state())
    for entry in _log_buffer[-100:]:
        socketio.emit("log", entry)


def _ship_update_loop():
    while True:
        socketio.sleep(2)
        socketio.emit("ship_update", ship_sim.get_state())


def _interface_status_loop():
    while True:
        socketio.sleep(3)
        for iface in list(iface_mgr._interfaces.values()):
            socketio.emit("interface_status", iface.to_dict())


socketio.start_background_task(_ship_update_loop)
socketio.start_background_task(_interface_status_loop)


def open_browser():
    webbrowser.open("http://localhost:8972")

if __name__ == "__main__":
    print("NMEA 0183 船舶模拟系统启动中...")
    print(f"访问地址: http://localhost:8972")
    threading.Timer(1.5, open_browser).start()
    socketio.run(app, host="0.0.0.0", port=8972, debug=False)
