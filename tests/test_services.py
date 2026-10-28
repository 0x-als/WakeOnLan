import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ["PULSE_HOME"] = tempfile.mkdtemp(prefix="pulse-test-")
os.environ["PULSE_DRY_RUN"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config
from service.actions import DeviceActions
from service.agent import AgentClient
from service.devices import Device, DeviceRegistry
from service.discovery import DiscoveryResponder, NetworkScanner
from service.errors import ActionError, DeviceNotFound, DuplicateDevice
from service.identity import ServerIdentity
from service.mac import Mac
from service.monitor import DeviceMonitor
from service.network import ArpTable, Interface
from service.power import PowerService
from service.settings import Settings
from service.wake import MagicPacket, WakeService


class FakeNetwork:
    def __init__(self, interfaces=None):
        self._interfaces = interfaces or []

    def interfaces(self):
        return list(self._interfaces)

    def ips(self):
        return [item.ip for item in self._interfaces]

    def macs(self):
        return {item.mac for item in self._interfaces if item.mac}

    def hostname(self):
        return "TEST-PC"

    def ordered_ips(self):
        return self.ips()

    def primary_ip(self):
        return self.ips()[0] if self._interfaces else "127.0.0.1"


class FakeSettings:
    def __init__(self):
        self.server_id = "server-1"
        self.server_name = "TEST-PC"
        self.token = "secret12"
        self.port = 8765


class AgentHandler(BaseHTTPRequestHandler):
    token = "secret12"
    calls = []

    def log_message(self, *args):
        pass

    def _send(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/health":
            self._send(200, {"app": "pulse", "name": "REMOTE"})
        else:
            self._send(404, {"detail": "no"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.headers.get("X-Pulse-Token") != self.token:
            self._send(401, {"detail": "Неверный ключ доступа"})
            return
        AgentHandler.calls.append((self.path, body))
        self._send(200, {"ok": True})


class MacTests(unittest.TestCase):
    def test_normalize_accepts_common_formats(self):
        for raw in ("aa-bb-cc-dd-ee-ff", "AABBCCDDEEFF", "aa:bb:cc:dd:ee:ff", "aabb.ccdd.eeff"):
            self.assertEqual(Mac.normalize(raw), "AA:BB:CC:DD:EE:FF")

    def test_normalize_rejects_garbage(self):
        for raw in ("", "12345", "AA:BB:CC:DD:EE:GG", None):
            with self.assertRaises(ValueError):
                Mac.normalize(raw)

    def test_usable(self):
        self.assertFalse(Mac.is_usable("FF:FF:FF:FF:FF:FF"))
        self.assertFalse(Mac.is_usable("01:00:5E:00:00:FB"))
        self.assertFalse(Mac.is_usable("00:00:00:00:00:00"))
        self.assertTrue(Mac.is_usable("3C:52:82:11:22:33"))


class MagicPacketTests(unittest.TestCase):
    def test_packet_layout(self):
        packet = MagicPacket.build("AA:BB:CC:DD:EE:FF")
        self.assertEqual(len(packet), 102)
        self.assertEqual(packet[:6], b"\xff" * 6)
        self.assertEqual(packet[6:12], bytes.fromhex("AABBCCDDEEFF"))
        self.assertEqual(packet[6:], bytes.fromhex("AABBCCDDEEFF") * 16)

    def test_packet_is_really_sent(self):
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(2)
        port = receiver.getsockname()[1]
        sent = WakeService(FakeNetwork()).wake("AA:BB:CC:DD:EE:FF", "127.0.0.1", port)
        data, _ = receiver.recvfrom(2048)
        receiver.close()
        self.assertEqual(sent, Config.WOL_REPEATS)
        self.assertEqual(data, MagicPacket.build("AA:BB:CC:DD:EE:FF"))

    def test_directed_broadcast_routes_added_for_default(self):
        interface = Interface("Wi-Fi", "192.168.1.20", "255.255.255.0", "AA:BB:CC:00:00:01")
        routes = WakeService(FakeNetwork([interface]))._routes(Config.DEFAULT_BROADCAST)
        self.assertIn(("192.168.1.20", "192.168.1.255"), routes)
        self.assertIn((None, "255.255.255.255"), routes)


class SettingsTests(unittest.TestCase):
    def test_first_load_generates_and_persists(self):
        settings = Settings.load()
        self.assertTrue(settings.token and settings.server_id and settings.server_name)
        self.assertEqual(len(settings.token), Config.TOKEN_LENGTH)
        again = Settings.load()
        self.assertEqual(again.token, settings.token)
        self.assertEqual(again.server_id, settings.server_id)

    def test_broken_file_falls_back(self):
        Config.CONFIG_FILE.write_text("{not json", encoding="utf-8")
        settings = Settings.load()
        self.assertTrue(settings.token)
        self.assertEqual(settings.devices, [])


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()
        self.settings.devices = []
        self.settings.save = lambda: None
        self.registry = DeviceRegistry(self.settings)

    def data(self, **extra):
        base = {"name": "PC", "mac": "aa-bb-cc-dd-ee-ff", "host": "192.168.1.50"}
        base.update(extra)
        return base

    def test_crud(self):
        device = self.registry.add(self.data())
        self.assertEqual(device.mac, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(self.registry.get(device.id).name, "PC")
        updated = self.registry.update(device.id, self.data(name="Office", agent=True))
        self.assertEqual((updated.name, updated.agent), ("Office", True))
        self.registry.remove(device.id)
        with self.assertRaises(DeviceNotFound):
            self.registry.get(device.id)

    def test_duplicate_mac(self):
        self.registry.add(self.data())
        with self.assertRaises(DuplicateDevice):
            self.registry.add(self.data(name="Copy", mac="AABBCCDDEEFF"))

    def test_update_to_foreign_mac_rejected(self):
        first = self.registry.add(self.data())
        second = self.registry.add(self.data(name="B", mac="11:22:33:44:55:66"))
        with self.assertRaises(DuplicateDevice):
            self.registry.update(second.id, self.data(name="B", mac=first.mac))

    def test_find_by_mac_ignores_bad_input(self):
        self.assertIsNone(self.registry.find_by_mac("nonsense"))


class ArpTests(unittest.TestCase):
    WINDOWS = """
Interface: 192.168.1.20 --- 0x7
  Internet Address      Physical Address      Type
  192.168.1.1           3c-52-82-11-22-33     dynamic
  192.168.1.77          aa-bb-cc-dd-ee-ff     динамический
  192.168.1.255         ff-ff-ff-ff-ff-ff     static
  224.0.0.22            01-00-5e-00-00-16     static
"""
    LINUX = """? (192.168.1.1) at 3c:52:82:11:22:33 [ether] on wlan0
? (192.168.1.9) at <incomplete> on wlan0
? (192.168.1.77) at aa:bb:cc:dd:ee:ff [ether] on wlan0
"""

    def test_windows_output(self):
        table = ArpTable().parse(self.WINDOWS)
        self.assertEqual(table, {"192.168.1.1": "3C:52:82:11:22:33", "192.168.1.77": "AA:BB:CC:DD:EE:FF"})

    def test_linux_output(self):
        table = ArpTable().parse(self.LINUX)
        self.assertEqual(sorted(table), ["192.168.1.1", "192.168.1.77"])


class DiscoveryTests(unittest.TestCase):
    def test_responder_answers_query(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
        probe.close()
        original = Config.DISCOVERY_PORT
        Config.DISCOVERY_PORT = free_port
        interface = Interface("Wi-Fi", "192.168.1.20", "255.255.255.0", "AA:BB:CC:00:00:01")
        identity = ServerIdentity(FakeSettings(), FakeNetwork([interface]))
        responder = DiscoveryResponder(identity)
        try:
            self.assertTrue(responder.start())
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(2)
            client.sendto(Config.DISCOVERY_QUERY, ("127.0.0.1", free_port))
            data, _ = client.recvfrom(4096)
            client.close()
            info = json.loads(data)
            self.assertEqual(info["app"], "pulse")
            self.assertEqual(info["id"], "server-1")
            self.assertIn("AA:BB:CC:00:00:01", info["macs"])
        finally:
            responder.stop()
            Config.DISCOVERY_PORT = original

    def test_responder_ignores_other_packets(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
        probe.close()
        original = Config.DISCOVERY_PORT
        Config.DISCOVERY_PORT = free_port
        responder = DiscoveryResponder(ServerIdentity(FakeSettings(), FakeNetwork()))
        try:
            responder.start()
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(0.6)
            client.sendto(b"hello", ("127.0.0.1", free_port))
            with self.assertRaises(socket.timeout):
                client.recvfrom(1024)
            client.close()
        finally:
            responder.stop()
            Config.DISCOVERY_PORT = original

    def test_scanner_merges_agents_and_arp(self):
        interface = Interface("Wi-Fi", "192.168.1.20", "255.255.255.0", "AA:BB:CC:00:00:01")
        network = FakeNetwork([interface])
        settings = FakeSettings()
        identity = ServerIdentity(settings, network)

        class Arp:
            def read(self):
                return {
                    "192.168.1.1": "3C:52:82:11:22:33",
                    "192.168.1.77": "AA:BB:CC:DD:EE:FF",
                    "10.0.0.5": "AA:BB:CC:DD:EE:01",
                }

        class Resolver:
            def resolve(self, addresses):
                return {"192.168.1.1": "router"}

        registry = DeviceRegistry(settings_with_devices([{"id": "x", "name": "n", "mac": "3C:52:82:11:22:33"}]))
        scanner = NetworkScanner(network, identity, registry, Arp(), Resolver())
        replies = {
            "192.168.1.77": {"app": "pulse", "id": "other", "name": "GAMING-PC", "port": 8765, "macs": ["AA:BB:CC:DD:EE:FF"]},
            "192.168.1.20": {"app": "pulse", "id": "server-1", "name": "TEST-PC", "port": 8765, "macs": ["AA:BB:CC:00:00:01"]},
        }
        scanner._collect = lambda interfaces, networks: replies
        devices, networks = scanner.scan()
        by_host = {item["host"]: item for item in devices}
        self.assertEqual(networks, ["192.168.1.0/24"])
        self.assertNotIn("10.0.0.5", by_host)
        self.assertEqual(by_host["192.168.1.77"]["name"], "GAMING-PC")
        self.assertTrue(by_host["192.168.1.77"]["agent"])
        self.assertFalse(by_host["192.168.1.77"]["is_self"])
        self.assertTrue(by_host["192.168.1.20"]["is_self"])
        self.assertEqual(by_host["192.168.1.1"]["name"], "router")
        self.assertTrue(by_host["192.168.1.1"]["added"])
        self.assertFalse(by_host["192.168.1.77"]["added"])


def settings_with_devices(devices):
    settings = Settings()
    settings.devices = devices
    settings.save = lambda: None
    return settings


class AgentAndActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = HTTPServer(("0.0.0.0", 0), AgentHandler)
        cls.port = cls.http.server_address[1]
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()

    def setUp(self):
        AgentHandler.calls.clear()
        interface = Interface("Wi-Fi", "192.168.1.20", "255.255.255.0", "AA:BB:CC:00:00:01")
        self.network = FakeNetwork([interface])
        self.settings = FakeSettings()
        self.identity = ServerIdentity(self.settings, self.network)
        self.agent = AgentClient()

        class FakeWake:
            sent = []

            def wake(self, mac, broadcast, port):
                self.sent.append((mac, broadcast, port))
                return 3

        self.fake_wake = FakeWake()
        self.actions = DeviceActions(self.settings, self.identity, self.fake_wake, PowerService(), self.agent)

    def remote(self, **extra):
        data = dict(id="r1", name="Remote", mac="11:22:33:44:55:66", host="127.0.0.2", port=self.port, agent=True)
        data.update(extra)
        return Device(**data)

    def test_health(self):
        self.assertEqual(self.agent.health("127.0.0.2", self.port)["name"], "REMOTE")
        self.assertIsNone(self.agent.health("127.0.0.1", 1))

    def test_wake_remote_device(self):
        result = self.actions.wake(self.remote(broadcast="192.168.1.255", wol_port=7))
        self.assertEqual(result, 3)
        self.assertEqual(self.fake_wake.sent, [("11:22:33:44:55:66", "192.168.1.255", 7)])

    def test_wake_self_is_rejected(self):
        own = Device(id="s", name="Me", mac="AA:BB:CC:00:00:01", host="192.168.1.20")
        with self.assertRaises(ActionError) as caught:
            self.actions.wake(own)
        self.assertEqual(caught.exception.status, 409)

    def test_shutdown_self_runs_locally_in_dry_run(self):
        own = Device(id="s", name="Me", mac="AA:BB:CC:00:00:01", host="192.168.1.20")
        self.actions.shutdown(own, 10, False)
        self.assertEqual(AgentHandler.calls, [])

    def test_shutdown_forwarded_with_token(self):
        self.actions.shutdown(self.remote(), 15, True)
        self.assertEqual(AgentHandler.calls, [("/api/shutdown", {"delay": 15, "force": True})])

    def test_cancel_forwarded(self):
        self.actions.cancel(self.remote())
        self.assertEqual(AgentHandler.calls[0][0], "/api/shutdown/cancel")

    def test_wrong_token_reports_clear_error(self):
        self.settings.token = "wrong"
        with self.assertRaises(ActionError) as caught:
            self.actions.shutdown(self.remote(), 5)
        self.assertIn("ключ", caught.exception.message.lower())

    def test_device_token_overrides_hub_token(self):
        self.settings.token = "wrong"
        self.actions.shutdown(self.remote(token="secret12"), 5)
        self.assertEqual(len(AgentHandler.calls), 1)

    def test_unreachable_agent(self):
        with self.assertRaises(ActionError) as caught:
            self.actions.shutdown(self.remote(port=1), 5)
        self.assertEqual(caught.exception.status, 504)

    def test_device_without_agent_cannot_be_shut_down(self):
        with self.assertRaises(ActionError) as caught:
            self.actions.shutdown(self.remote(agent=False), 5)
        self.assertEqual(caught.exception.status, 409)


class MonitorTests(unittest.TestCase):
    def setUp(self):
        interface = Interface("Wi-Fi", "192.168.1.20", "255.255.255.0", "AA:BB:CC:00:00:01")
        self.identity = ServerIdentity(FakeSettings(), FakeNetwork([interface]))

        class Agent:
            alive = set()

            def health(self, host, port):
                return {"app": "pulse"} if host in self.alive else None

        self.agent = Agent()
        self.monitor = DeviceMonitor(self.agent, self.identity)
        self.monitor.ping = lambda host: host == "192.168.1.60"
        self.monitor.probe = lambda host: host == "192.168.1.61"

    def test_statuses(self):
        self.agent.alive = {"192.168.1.50"}
        own = Device(id="a", name="Me", mac="AA:BB:CC:00:00:01", host="192.168.1.20")
        agent_on = Device(id="b", name="B", mac="11:11:11:11:11:11", host="192.168.1.50", agent=True)
        agent_down = Device(id="c", name="C", mac="22:22:22:22:22:22", host="192.168.1.51", agent=True)
        ping_only = Device(id="d", name="D", mac="33:33:33:33:33:33", host="192.168.1.60")
        probe_only = Device(id="e", name="E", mac="44:44:44:44:44:44", host="192.168.1.61")
        offline = Device(id="f", name="F", mac="55:55:55:55:55:55", host="192.168.1.99")
        unknown = Device(id="g", name="G", mac="66:66:66:66:66:66")
        result = self.monitor.check_all([own, agent_on, agent_down, ping_only, probe_only, offline, unknown])
        self.assertEqual(result["a"], {"online": True, "is_self": True, "agent_up": True})
        self.assertEqual(result["b"], {"online": True, "is_self": False, "agent_up": True})
        self.assertEqual(result["c"], {"online": False, "is_self": False, "agent_up": False})
        self.assertTrue(result["d"]["online"] and not result["d"]["agent_up"])
        self.assertTrue(result["e"]["online"])
        self.assertFalse(result["f"]["online"])
        self.assertIsNone(result["g"]["online"])


if __name__ == "__main__":
    unittest.main()
