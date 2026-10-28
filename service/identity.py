import json
import platform

from config import Config


class ServerIdentity:
    def __init__(self, settings, network):
        self.settings = settings
        self.network = network

    @property
    def name(self):
        return self.settings.server_name or self.network.hostname()

    def ips(self):
        return set(self.network.ips()) | {"127.0.0.1"}

    def macs(self):
        return self.network.macs()

    def is_self(self, device):
        if device.mac and device.mac in self.macs():
            return True
        host = (device.host or "").strip().lower()
        if not host:
            return False
        return host in self.ips() or host in ("localhost", self.network.hostname().lower())

    def brief(self):
        return {
            "app": Config.APP_ID,
            "version": Config.VERSION,
            "id": self.settings.server_id,
            "name": self.name,
        }

    def info(self):
        data = self.brief()
        data.update(
            hostname=self.network.hostname(),
            os=platform.system(),
            port=self.settings.port,
            macs=sorted(self.macs()),
            ips=self.network.ordered_ips(),
        )
        return data

    def urls(self):
        return [f"http://{ip}:{self.settings.port}" for ip in self.network.ordered_ips()]

    def beacon(self):
        return json.dumps(self.info(), ensure_ascii=False).encode("utf-8")
