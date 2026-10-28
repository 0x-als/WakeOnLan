import ipaddress
import json
import logging
import socket
import threading
import time
from dataclasses import asdict, dataclass

from config import Config


@dataclass
class FoundDevice:
    name: str
    host: str
    mac: str
    port: int
    agent: bool
    is_self: bool
    added: bool = False

    def to_dict(self):
        return asdict(self)


class DiscoveryResponder:
    def __init__(self, identity):
        self.identity = identity
        self.sock = None
        self.thread = None
        self.running = False

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", Config.DISCOVERY_PORT))
            sock.settimeout(1.0)
        except OSError as error:
            sock.close()
            logging.warning("Ответчик поиска не запущен: %s", error)
            return False
        self.sock = sock
        self.running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def _serve(self):
        while self.running:
            try:
                data, address = self.sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break
            if data.strip() != Config.DISCOVERY_QUERY:
                continue
            try:
                self.sock.sendto(self.identity.beacon(), address)
            except OSError:
                continue


class NetworkScanner:
    def __init__(self, network, identity, registry, arp, resolver):
        self.network = network
        self.identity = identity
        self.registry = registry
        self.arp = arp
        self.resolver = resolver

    def scan(self):
        interfaces = self.network.interfaces()
        networks = [interface.scan_network for interface in interfaces]
        replies = self._collect(interfaces, networks)
        table = self.arp.read()
        found = self._merge(interfaces, networks, table, replies)
        names = self.resolver.resolve([item.host for item in found.values() if not item.name])
        for item in found.values():
            if not item.name:
                item.name = names.get(item.host, "")
            item.added = self.registry.find_by_mac(item.mac) is not None
        return [item.to_dict() for item in found.values()], [str(net) for net in networks]

    def _collect(self, interfaces, networks):
        replies = {}
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.2)
            self._poke(networks)
            self._query(sock, interfaces)
            started = time.time()
            second_poke = False
            while time.time() - started < Config.SCAN_WAIT:
                if not second_poke and time.time() - started > Config.SCAN_WAIT / 2:
                    self._poke(networks)
                    self._query(sock, interfaces)
                    second_poke = True
                try:
                    data, address = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                info = self._parse(data)
                if info:
                    replies[address[0]] = info
        finally:
            sock.close()
        return replies

    @staticmethod
    def _poke(networks):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            for network in networks:
                for host in network.hosts():
                    try:
                        sock.sendto(b"\x00", (str(host), 9))
                    except OSError:
                        pass
        finally:
            sock.close()

    @staticmethod
    def _query(sock, interfaces):
        targets = {Config.DEFAULT_BROADCAST} | {interface.broadcast for interface in interfaces}
        for target in targets:
            try:
                sock.sendto(Config.DISCOVERY_QUERY, (target, Config.DISCOVERY_PORT))
            except OSError:
                pass

    @staticmethod
    def _parse(data):
        try:
            info = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        if isinstance(info, dict) and info.get("app") == Config.APP_ID:
            return info
        return None

    def _merge(self, interfaces, networks, table, replies):
        own = {interface.ip: interface.mac for interface in interfaces}
        found = {}
        for ip, mac in table.items():
            if ip in own or not self._in_networks(ip, networks):
                continue
            found[ip] = FoundDevice("", ip, mac, Config.PORT, False, False)
        for ip, info in replies.items():
            macs = [str(item) for item in info.get("macs", []) if item]
            mac = table.get(ip) or own.get(ip) or (macs[0] if macs else "")
            if not mac:
                continue
            is_self = info.get("id") == self.identity.settings.server_id or ip in own
            found[ip] = FoundDevice(
                str(info.get("name", "")), ip, mac, int(info.get("port") or Config.PORT),
                True, is_self,
            )
        if not any(item.is_self for item in found.values()):
            for interface in interfaces:
                if interface.mac:
                    found[interface.ip] = FoundDevice(
                        self.identity.name, interface.ip, interface.mac,
                        self.identity.settings.port, True, True,
                    )
                    break
        return found

    @staticmethod
    def _in_networks(ip, networks):
        address = ipaddress.ip_address(ip)
        return any(address in network for network in networks)
