import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

from config import Config
from service.network import hidden_window_flags


class DeviceMonitor:
    def __init__(self, agent, identity):
        self.agent = agent
        self.identity = identity

    def check(self, device):
        if self.identity.is_self(device):
            return {"online": True, "is_self": True, "agent_up": True}
        host = (device.host or "").strip()
        if not host:
            return {"online": None, "is_self": False, "agent_up": False}
        if device.agent:
            agent_up = self.agent.health(host, device.port) is not None
            online = agent_up or self.ping(host)
        else:
            agent_up = False
            online = self.ping(host) or self.probe(host)
        return {"online": online, "is_self": False, "agent_up": agent_up}

    def check_all(self, devices):
        if not devices:
            return {}
        with ThreadPoolExecutor(max_workers=min(16, len(devices))) as pool:
            results = list(pool.map(self.check, devices))
        return {device.id: result for device, result in zip(devices, results)}

    @staticmethod
    def ping(host):
        if Config.IS_WIN:
            command = ["ping", "-n", "1", "-w", str(Config.PING_TIMEOUT_MS), host]
        else:
            command = ["ping", "-c", "1", "-W", "1", host]
        try:
            result = subprocess.run(
                command, capture_output=True, timeout=4, creationflags=hidden_window_flags()
            )
        except Exception:
            return False
        return b"ttl=" in result.stdout.lower()

    @staticmethod
    def _connect(host, port):
        try:
            with socket.create_connection((host, port), timeout=Config.PROBE_TIMEOUT):
                return True
        except ConnectionRefusedError:
            return True
        except OSError:
            return False

    def probe(self, host):
        ports = Config.PROBE_PORTS
        with ThreadPoolExecutor(max_workers=len(ports)) as pool:
            return any(pool.map(lambda port: self._connect(host, port), ports))
