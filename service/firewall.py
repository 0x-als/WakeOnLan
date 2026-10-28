import ctypes
import os
import subprocess
import sys

from config import Config
from service.network import hidden_window_flags


class FirewallManager:
    def __init__(self, script_path):
        self.script_path = os.path.abspath(script_path)

    @staticmethod
    def is_admin():
        if not Config.IS_WIN:
            return False
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    @staticmethod
    def rules(port):
        return (
            (f"{Config.APP_NAME} HTTP", "TCP", port),
            (f"{Config.APP_NAME} Discovery", "UDP", Config.DISCOVERY_PORT),
        )

    def add_rules(self, port):
        ok = True
        for name, protocol, number in self.rules(port):
            self._netsh(["delete", "rule", f"name={name}"])
            ok = self._netsh([
                "add", "rule", f"name={name}", "dir=in", "action=allow",
                f"protocol={protocol}", f"localport={number}", "profile=any",
            ]) and ok
        return ok

    def remove_rules(self, port):
        for name, _protocol, _number in self.rules(port):
            self._netsh(["delete", "rule", f"name={name}"])
        return True

    def elevate(self, argument):
        if not Config.IS_WIN:
            return False
        if getattr(sys, "frozen", False):
            params = argument
        else:
            params = f'"{self.script_path}" {argument}'
        try:
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        except Exception:
            return False
        return result > 32

    @staticmethod
    def _netsh(args):
        try:
            result = subprocess.run(
                ["netsh", "advfirewall", "firewall", *args],
                capture_output=True, timeout=20, creationflags=hidden_window_flags(),
            )
        except Exception:
            return False
        return result.returncode == 0
