from typing import Optional

from fastapi import APIRouter, Depends

from api.schemas import DeviceIn, ShutdownIn


class DevicesRoutes:
    def __init__(self, services, guard):
        self.services = services
        self.router = APIRouter(
            prefix="/api/devices", tags=["devices"], dependencies=[Depends(guard)]
        )
        self.router.add_api_route("", self.list_devices, methods=["GET"])
        self.router.add_api_route("", self.create_device, methods=["POST"], status_code=201)
        self.router.add_api_route("/{device_id}", self.update_device, methods=["PUT"])
        self.router.add_api_route("/{device_id}", self.delete_device, methods=["DELETE"])
        self.router.add_api_route("/{device_id}/wake", self.wake, methods=["POST"])
        self.router.add_api_route("/{device_id}/shutdown", self.shutdown, methods=["POST"])
        self.router.add_api_route("/{device_id}/cancel", self.cancel, methods=["POST"])

    def view(self, device, status):
        data = device.to_dict()
        data["has_token"] = bool(data.pop("token"))
        online = status["online"]
        data.update(
            online=online,
            is_self=status["is_self"],
            agent_up=status["agent_up"],
            can_shutdown=status["is_self"] or (device.agent and status["agent_up"]),
        )
        return data

    def list_devices(self):
        devices = self.services.registry.all()
        statuses = self.services.monitor.check_all(devices)
        return [self.view(device, statuses[device.id]) for device in devices]

    def create_device(self, payload: DeviceIn):
        device = self.services.registry.add(payload.model_dump())
        return self.view(device, self.services.monitor.check(device))

    def update_device(self, device_id: str, payload: DeviceIn):
        device = self.services.registry.update(device_id, payload.model_dump(exclude_unset=True))
        return self.view(device, self.services.monitor.check(device))

    def delete_device(self, device_id: str):
        self.services.registry.remove(device_id)
        return {"ok": True}

    def wake(self, device_id: str):
        device = self.services.registry.get(device_id)
        sent = self.services.actions.wake(device)
        return {"ok": True, "sent": sent, "mac": device.mac}

    def shutdown(self, device_id: str, payload: Optional[ShutdownIn] = None):
        device = self.services.registry.get(device_id)
        options = payload or ShutdownIn()
        self.services.actions.shutdown(device, options.delay, options.force)
        return {"ok": True, "delay": options.delay}

    def cancel(self, device_id: str):
        device = self.services.registry.get(device_id)
        self.services.actions.cancel(device)
        return {"ok": True}
