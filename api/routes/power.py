from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import ShutdownIn, WakeIn


class PowerRoutes:
    def __init__(self, services, guard):
        self.services = services
        self.router = APIRouter(prefix="/api", tags=["power"], dependencies=[Depends(guard)])
        self.router.add_api_route("/shutdown", self.shutdown, methods=["POST"])
        self.router.add_api_route("/shutdown/cancel", self.cancel, methods=["POST"])
        self.router.add_api_route("/wake", self.wake, methods=["POST"])

    def shutdown(self, payload: Optional[ShutdownIn] = None):
        options = payload or ShutdownIn()
        self.services.power.shutdown(options.delay, options.force)
        return {"ok": True, "delay": options.delay}

    def cancel(self):
        self.services.power.cancel()
        return {"ok": True}

    def wake(self, payload: WakeIn):
        try:
            sent = self.services.wake.wake(payload.mac, payload.broadcast, payload.port)
        except OSError as error:
            raise HTTPException(status_code=500, detail=f"Не удалось отправить пакет: {error}")
        return {"ok": True, "sent": sent, "mac": payload.mac}
