import socket
import threading
import time
import random
import string
from datetime import datetime, timezone


def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _gen_id():
    return "iface_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


class Interface:
    def __init__(self, name, protocol, ip, port, formats, ship_sim, nmea_gen, log_cb, iface_id=None, created_at=None):
        self.id = iface_id if iface_id else _gen_id()
        self.name = name
        self.protocol = protocol
        self.ip = ip
        self.port = port
        self.formats = list(formats)
        self.ship_sim = ship_sim
        self.nmea_gen = nmea_gen
        self._log_cb = log_cb

        self.status = "disconnected"
        self.total_connections = 0
        self.interruptions = 0
        self.data_count = 0
        self.created_at = created_at if created_at else _now_str()
        self.last_connected_at = None
        self.last_disconnected_at = None
        self.interruption_logs = []

        self._stop_evt = threading.Event()
        self._thread = None
        self._server_sock = None
        self._udp_sock = None
        self._clients = []
        self._clients_lock = threading.Lock()
        self._stats_lock = threading.Lock()

    def _log(self, level, message, nmea_raw=None):
        if self._log_cb:
            self._log_cb(self.id, self.name, level, message, nmea_raw)

    def _add_interruption(self, reason):
        with self._stats_lock:
            self.interruptions += 1
            self.interruption_logs.insert(0, {"time": _now_str(), "reason": reason})
            if len(self.interruption_logs) > 50:
                self.interruption_logs = self.interruption_logs[:50]
        self._log("warn", f"连接中断: {reason}")

    def connect(self):
        if self.status in ("connected", "connecting"):
            return False
        self._stop_evt.clear()
        self.status = "connecting"
        self._log("info", f"正在启动 {self.protocol} 接口 {self.ip}:{self.port}")
        with self._stats_lock:
            self.total_connections += 1
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def disconnect(self):
        self._stop_evt.set()
        self._cleanup_sockets()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        was_active = self.status in ("connected", "connecting", "error")
        self.status = "disconnected"
        if was_active:
            self.last_disconnected_at = _now_str()
            self._log("info", f"接口 {self.name} 已断开")
        return True

    def delete(self):
        self.disconnect()
        self._log("info", f"接口 {self.name} 已删除")

    def update_config(self, name, protocol, ip, port, formats):
        was_connected = self.status in ("connected", "connecting")
        if was_connected:
            self.disconnect()
        self.name = name
        self.protocol = protocol
        self.ip = ip
        self.port = port
        self.formats = list(formats)
        self._log("info", f"接口配置已更新")
        return was_connected

    def _cleanup_sockets(self):
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None
        with self._clients_lock:
            for c in self._clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()
        if self._udp_sock:
            try:
                self._udp_sock.close()
            except Exception:
                pass
            self._udp_sock = None

    def _run(self):
        try:
            time.sleep(0.3)
            if self.protocol == "TCP":
                self._run_tcp()
            else:
                self._run_udp()
        except OSError as e:
            self.status = "error"
            self._add_interruption(f"套接字错误: {e}")
        except Exception as e:
            self.status = "error"
            self._add_interruption(f"未知错误: {e}")

    def _run_tcp(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.ip, self.port))
        srv.listen(5)
        srv.settimeout(0.5)
        self._server_sock = srv
        self.status = "connected"
        self.last_connected_at = _now_str()
        self._log("success", f"TCP 服务器已启动，监听 {self.ip}:{self.port}")

        accept_thread = threading.Thread(target=self._tcp_accept, daemon=True)
        accept_thread.start()

        while not self._stop_evt.is_set():
            self._send_data()
            self._stop_evt.wait(1.0)

        accept_thread.join(timeout=2)

    def _tcp_accept(self):
        while not self._stop_evt.is_set() and self._server_sock:
            try:
                client, addr = self._server_sock.accept()
                with self._clients_lock:
                    self._clients.append(client)
                self._log("info", f"客户端已连接: {addr[0]}:{addr[1]}")
            except socket.timeout:
                continue
            except OSError:
                break

    def _run_udp(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if self.ip and self.ip != "0.0.0.0":
            try:
                sock.bind((self.ip, 0))
            except OSError:
                pass
        self._udp_sock = sock
        self.status = "connected"
        self.last_connected_at = _now_str()
        self._log("success", f"UDP 广播已启动，广播端口 {self.port}，源地址 {self.ip}")

        while not self._stop_evt.is_set():
            self._send_data()
            self._stop_evt.wait(1.0)

    def _send_data(self):
        state = self.ship_sim.state
        state.utc_time = datetime.now(timezone.utc)
        for fmt in self.formats:
            sentences = self.nmea_gen.generate(fmt, state)
            if not sentences:
                continue
            for sentence in sentences:
                raw = sentence.strip()
                if self.protocol == "TCP":
                    self._tcp_broadcast(raw)
                else:
                    self._udp_send(raw)
                with self._stats_lock:
                    self.data_count += 1
                self._log("data", raw, nmea_raw=raw)

    def _tcp_broadcast(self, data):
        payload = (data + "\r\n").encode("ascii")
        dead = []
        with self._clients_lock:
            clients = list(self._clients)
        for i, client in enumerate(clients):
            try:
                client.sendall(payload)
            except Exception as e:
                dead.append(i)
                self._log("warn", f"客户端断开: {e}")
                self._add_interruption(f"TCP客户端断开: {e}")
                try:
                    client.close()
                except Exception:
                    pass
        if dead:
            with self._clients_lock:
                remaining = []
                for i, c in enumerate(self._clients):
                    if i not in dead:
                        remaining.append(c)
                self._clients = remaining

    def _udp_send(self, data):
        if not self._udp_sock:
            return
        payload = (data + "\r\n").encode("ascii")
        try:
            self._udp_sock.sendto(payload, ("<broadcast>", self.port))
        except Exception as e:
            self._add_interruption(f"UDP广播失败: {e}")

    def to_dict(self):
        with self._stats_lock:
            return {
                "id": self.id,
                "name": self.name,
                "protocol": self.protocol,
                "ip": self.ip,
                "port": self.port,
                "formats": list(self.formats),
                "status": self.status,
                "total_connections": self.total_connections,
                "interruptions": self.interruptions,
                "data_count": self.data_count,
                "created_at": self.created_at,
                "last_connected_at": self.last_connected_at,
                "last_disconnected_at": self.last_disconnected_at,
                "interruption_logs": list(self.interruption_logs),
                "connected_clients": len(self._clients) if self.protocol == "TCP" else 0,
            }


class InterfaceManager:
    def __init__(self, ship_sim, nmea_gen, log_cb):
        self.ship_sim = ship_sim
        self.nmea_gen = nmea_gen
        self.log_cb = log_cb
        self._interfaces = {}
        self._lock = threading.Lock()

    def create(self, name, protocol, ip, port, formats, auto_connect=True, iface_id=None, created_at=None):
        with self._lock:
            iface = Interface(name, protocol, ip, port, formats, self.ship_sim, self.nmea_gen, self.log_cb, iface_id=iface_id, created_at=created_at)
            self._interfaces[iface.id] = iface
        if auto_connect:
            iface.connect()
        return iface

    def get(self, iface_id):
        return self._interfaces.get(iface_id)

    def list(self):
        with self._lock:
            return [iface.to_dict() for iface in self._interfaces.values()]

    def update(self, iface_id, name, protocol, ip, port, formats):
        iface = self._interfaces.get(iface_id)
        if not iface:
            return None
        was_connected = iface.update_config(name, protocol, ip, port, formats)
        return iface.to_dict()

    def delete(self, iface_id):
        with self._lock:
            iface = self._interfaces.pop(iface_id, None)
        if iface:
            iface.delete()
            return True
        return False

    def connect(self, iface_id):
        iface = self._interfaces.get(iface_id)
        if iface:
            return iface.connect()
        return False

    def disconnect(self, iface_id):
        iface = self._interfaces.get(iface_id)
        if iface:
            return iface.disconnect()
        return False
