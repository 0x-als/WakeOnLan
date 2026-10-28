import socket
import time

from config import Config
from service.mac import Mac


class MagicPacket:
    @staticmethod
    def build(mac):
        return b"\xff" * 6 + Mac.to_bytes(mac) * 16


class WakeService:
    def __init__(self, network):
        self.network = network

    def wake(self, mac, broadcast=None, port=None):
        packet = MagicPacket.build(mac)
        target = (broadcast or Config.DEFAULT_BROADCAST).strip()
        number = int(port or Config.DEFAULT_WOL_PORT)
        sent = 0
        for source, destination in self._routes(target):
            sent += self._send(packet, source, destination, number)
        if sent == 0:
            raise OSError("сеть недоступна")
        return sent

    def _routes(self, target):
        routes = [(None, target)]
        for interface in self.network.interfaces():
            routes.append((interface.ip, target))
            if target == Config.DEFAULT_BROADCAST:
                routes.append((interface.ip, interface.broadcast))
        return list(dict.fromkeys(routes))

    @staticmethod
    def _send(packet, source, destination, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        count = 0
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            if source:
                sock.bind((source, 0))
            for _ in range(Config.WOL_REPEATS):
                sock.sendto(packet, (destination, port))
                count += 1
                time.sleep(0.03)
        except OSError:
            pass
        finally:
            sock.close()
        return count
