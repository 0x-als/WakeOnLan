from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from config import Config


class ShortcutsRoutes:
    def __init__(self, services, guard):
        self.services = services
        self.router = APIRouter(
            prefix="/api/shortcuts", tags=["shortcuts"], dependencies=[Depends(guard)]
        )
        self.router.add_api_route("/wake/{device_id}", self.wake, methods=["GET", "POST"])
        self.router.add_api_route("/shutdown/{device_id}", self.shutdown, methods=["GET", "POST"])

    def wake(self, device_id: str):
        device = self.services.registry.get(device_id)
        self.services.actions.wake(device)
        return PlainTextResponse(f"Пакет включения отправлен: {device.name}")

    def shutdown(self, device_id: str):
        device = self.services.registry.get(device_id)
        self.services.actions.shutdown(device, Config.SHUTDOWN_DELAY, False)
        return PlainTextResponse(f"Выключение через {Config.SHUTDOWN_DELAY} с: {device.name}")
