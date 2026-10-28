import os
import sys
from pathlib import Path


class Config:
    APP_NAME = "Pulse"
    APP_ID = "pulse"
    VERSION = "1.0.0"
    IS_WIN = sys.platform == "win32"

    BASE_DIR = Path(__file__).resolve().parent
    WEB_DIR = BASE_DIR / "ui"

    HOST = "0.0.0.0"
    PORT = 8765
    DISCOVERY_PORT = 48765
    DISCOVERY_QUERY = b"PULSE_DISCOVER?"
    INSTANCE_PORT = 47654

    DEFAULT_BROADCAST = "255.255.255.255"
    DEFAULT_WOL_PORT = 9
    WOL_REPEATS = 3

    SHUTDOWN_DELAY = 10
    AGENT_TIMEOUT = 1.0
    PING_TIMEOUT_MS = 700
    PROBE_TIMEOUT = 0.35
    PROBE_PORTS = (445, 3389, 135, 139, 22)

    SCAN_WAIT = 1.8
    NAME_WAIT = 3.0
    MAX_PREFIX = 24
    IGNORED_INTERFACES = (
        "loopback", "vethernet", "virtualbox", "vmware", "vmnet", "bluetooth",
        "hyper-v", "docker", "wsl", "tailscale", "zerotier", "isatap", "teredo",
        "pseudo", "veth", "br-", "virbr",
    )

    TOKEN_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
    TOKEN_LENGTH = 8

    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    CONFIG_DIR = Path(
        os.environ.get("PULSE_HOME")
        or (Path(os.environ.get("APPDATA") or (Path.home() / ".config")) / APP_NAME)
    )
    CONFIG_FILE = CONFIG_DIR / "config.json"
    LOG_FILE = CONFIG_DIR / "pulse.log"

    DRY_RUN = os.environ.get("PULSE_DRY_RUN") == "1"
