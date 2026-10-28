from fastapi import APIRouter, Depends, HTTPException

from api.schemas import AutostartIn
from config import Config


class SystemRoutes:
    def __init__(self, services, guard):
        self.services = services
        self.router = APIRouter(tags=["system"])
        protected = [Depends(guard)]
        self.router.add_api_route("/api/health", self.health, methods=["GET"])
        self.router.add_api_route("/api/info", self.info, methods=["GET"], dependencies=protected)
        self.router.add_api_route(
            "/api/system/autostart", self.set_autostart, methods=["PUT"], dependencies=protected
        )

    def health(self):
        return self.services.identity.brief()

    def info(self):
        autostart = self.services.autostart
        data = self.services.identity.info()
        data.update(
            urls=self.services.identity.urls(),
            token=self.services.settings.token,
            autostart=autostart.is_enabled() if autostart.supported() else None,
            can_shutdown=True,
            app_name=Config.APP_NAME,
        )
        return data

    def set_autostart(self, payload: AutostartIn):
        autostart = self.services.autostart
        if not autostart.supported():
            raise HTTPException(status_code=501, detail="Автозапуск поддерживается только в Windows")
        if not autostart.set_enabled(payload.enabled):
            raise HTTPException(status_code=500, detail="Не удалось изменить автозапуск")
        return {"autostart": autostart.is_enabled()}
