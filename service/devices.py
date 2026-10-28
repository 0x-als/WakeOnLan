import uuid
from dataclasses import asdict, dataclass, fields

from config import Config
from service.errors import DeviceNotFound, DuplicateDevice
from service.mac import Mac


@dataclass
class Device:
    id: str
    name: str
    mac: str
    host: str = ""
    port: int = Config.PORT
    broadcast: str = Config.DEFAULT_BROADCAST
    wol_port: int = Config.DEFAULT_WOL_PORT
    agent: bool = False
    token: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        known = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in known})


class DeviceRegistry:
    EDITABLE = ("name", "mac", "host", "port", "broadcast", "wol_port", "agent", "token")

    def __init__(self, settings):
        self.settings = settings

    def all(self):
        with self.settings.lock:
            return [Device.from_dict(item) for item in self.settings.devices]

    def get(self, device_id):
        for device in self.all():
            if device.id == device_id:
                return device
        raise DeviceNotFound("Устройство не найдено")

    def find_by_mac(self, mac):
        try:
            wanted = Mac.normalize(mac)
        except ValueError:
            return None
        for device in self.all():
            if device.mac == wanted:
                return device
        return None

    def add(self, data):
        with self.settings.lock:
            mac = Mac.normalize(data["mac"])
            if self.find_by_mac(mac):
                raise DuplicateDevice("Устройство с таким MAC-адресом уже добавлено")
            device = Device(id=uuid.uuid4().hex[:12], **self._clean(data))
            device.mac = mac
            self.settings.devices.append(device.to_dict())
            self.settings.save()
            return device

    def update(self, device_id, data):
        with self.settings.lock:
            device = self.get(device_id)
            clean = self._clean(data)
            mac = Mac.normalize(clean["mac"])
            other = self.find_by_mac(mac)
            if other and other.id != device_id:
                raise DuplicateDevice("Устройство с таким MAC-адресом уже добавлено")
            for key, value in clean.items():
                setattr(device, key, value)
            device.mac = mac
            self._replace(device)
            return device

    def remove(self, device_id):
        with self.settings.lock:
            self.get(device_id)
            self.settings.devices = [
                item for item in self.settings.devices if item.get("id") != device_id
            ]
            self.settings.save()

    def _replace(self, device):
        for index, item in enumerate(self.settings.devices):
            if item.get("id") == device.id:
                self.settings.devices[index] = device.to_dict()
        self.settings.save()

    def _clean(self, data):
        return {key: data[key] for key in self.EDITABLE if key in data}
