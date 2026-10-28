import json
import logging
import os
import secrets
import socket
import threading
import uuid

from config import Config


class Settings:
    def __init__(self):
        self.lock = threading.RLock()
        self.server_id = ""
        self.server_name = ""
        self.token = ""
        self.port = Config.PORT
        self.devices = []
        self.autostart_initialized = False

    @staticmethod
    def new_token():
        return "".join(secrets.choice(Config.TOKEN_ALPHABET) for _ in range(Config.TOKEN_LENGTH))

    @classmethod
    def load(cls):
        settings = cls()
        data = {}
        try:
            data = json.loads(Config.CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        if not isinstance(data, dict):
            data = {}
        settings.server_id = str(data.get("server_id") or "")
        settings.server_name = str(data.get("server_name") or "")
        settings.token = str(data.get("token") or "")
        settings.port = data.get("port", Config.PORT)
        settings.devices = data.get("devices", [])
        settings.autostart_initialized = bool(data.get("autostart_initialized", False))
        changed = settings._ensure_defaults()
        if changed or not Config.CONFIG_FILE.exists():
            settings.save()
        return settings

    def _ensure_defaults(self):
        changed = False
        if not self.server_id:
            self.server_id = uuid.uuid4().hex
            changed = True
        if not self.token:
            self.token = self.new_token()
            changed = True
        if not self.server_name:
            self.server_name = socket.gethostname()
            changed = True
        if not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            self.port = Config.PORT
            changed = True
        if not isinstance(self.devices, list):
            self.devices = []
            changed = True
        return changed

    def to_dict(self):
        return {
            "server_id": self.server_id,
            "server_name": self.server_name,
            "token": self.token,
            "port": self.port,
            "devices": self.devices,
            "autostart_initialized": self.autostart_initialized,
        }

    def save(self):
        with self.lock:
            try:
                Config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                tmp = Config.CONFIG_FILE.with_suffix(".tmp")
                tmp.write_text(
                    json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
                )
                os.replace(tmp, Config.CONFIG_FILE)
            except Exception:
                logging.exception("Не удалось сохранить настройки")
