import ipaddress
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass

import psutil

from config import Config
from service.mac import Mac


def hidden_window_flags():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class Interface:
    name: str
    ip: str
    netmask: str
    mac: str

    @property
    def broadcast(self):
        network = ipaddress.ip_network(f"{self.ip}/{self.netmask}", strict=False)
        return str(network.broadcast_address)

    @property
    def scan_network(self):
        prefix = ipaddress.ip_network(f"0.0.0.0/{self.netmask}").prefixlen
        return ipaddress.ip_network(f"{self.ip}/{max(prefix, Config.MAX_PREFIX)}", strict=False)


class NetworkInfo:
    def interfaces(self):
        result = []
        try:
            addresses = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
        except Exception:
            return result
        for name, items in addresses.items():
            lowered = name.lower()
            if any(token in lowered for token in Config.IGNORED_INTERFACES):
                continue
            status = stats.get(name)
            if status is not None and not status.isup:
                continue
            mac = ""
            for item in items:
                if item.family == psutil.AF_LINK:
                    try:
                        mac = Mac.normalize(item.address)
                    except ValueError:
                        mac = ""
            for item in items:
                if item.family != socket.AF_INET or not item.netmask:
                    continue
                if item.address.startswith(("127.", "169.254.")):
                    continue
                result.append(Interface(name, item.address, item.netmask, mac))
        return result

    def ips(self):
        return [interface.ip for interface in self.interfaces()]

    def macs(self):
        return {interface.mac for interface in self.interfaces() if interface.mac}

    def hostname(self):
        return socket.gethostname()

    def primary_ip(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 1))
            return probe.getsockname()[0]
        except OSError:
            ips = self.ips()
            return ips[0] if ips else "127.0.0.1"
        finally:
            probe.close()

    def ordered_ips(self):
        primary = self.primary_ip()
        ips = self.ips()
        ordered = [primary] if primary in ips else []
        ordered += [ip for ip in ips if ip not in ordered]
        return ordered


class ArpTable:
    LINE = re.compile(
        r"(\d{1,3}(?:\.\d{1,3}){3})\)?\s+(?:at\s+)?([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})"
    )

    def parse(self, text):
        entries = {}
        for line in text.splitlines():
            match = self.LINE.search(line)
            if not match:
                continue
            ip, raw = match.groups()
            if not Mac.is_usable(raw):
                continue
            entries[ip] = Mac.normalize(raw)
        return entries

    def read(self):
        command = ["arp", "-a"] if Config.IS_WIN else ["arp", "-an"]
        try:
            result = subprocess.run(
                command, capture_output=True, timeout=6, creationflags=hidden_window_flags()
            )
        except Exception:
            return {}
        return self.parse(result.stdout.decode("utf-8", errors="ignore"))


class HostResolver:
    def resolve(self, addresses):
        names = {}
        if not addresses:
            return names
        pool = ThreadPoolExecutor(max_workers=24)
        try:
            futures = {pool.submit(self._lookup, ip): ip for ip in addresses}
            done, _ = wait(futures, timeout=Config.NAME_WAIT)
            for future in done:
                names[futures[future]] = future.result()
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return names

    @staticmethod
    def _lookup(ip):
        try:
            name = socket.gethostbyaddr(ip)[0]
        except (OSError, UnicodeError):
            return ""
        short = name.split(".")[0]
        return "" if short == ip or re.fullmatch(r"[\d-]+", short) else short
