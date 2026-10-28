from service.actions import DeviceActions
from service.agent import AgentClient
from service.autostart import AutostartManager
from service.devices import DeviceRegistry
from service.discovery import DiscoveryResponder, NetworkScanner
from service.identity import ServerIdentity
from service.monitor import DeviceMonitor
from service.network import ArpTable, HostResolver, NetworkInfo
from service.power import PowerService
from service.wake import WakeService


class Services:
    def __init__(self, settings, script_path):
        self.settings = settings
        self.network = NetworkInfo()
        self.identity = ServerIdentity(settings, self.network)
        self.registry = DeviceRegistry(settings)
        self.agent = AgentClient()
        self.wake = WakeService(self.network)
        self.power = PowerService()
        self.monitor = DeviceMonitor(self.agent, self.identity)
        self.actions = DeviceActions(settings, self.identity, self.wake, self.power, self.agent)
        self.scanner = NetworkScanner(
            self.network, self.identity, self.registry, ArpTable(), HostResolver()
        )
        self.responder = DiscoveryResponder(self.identity)
        self.autostart = AutostartManager(script_path)
