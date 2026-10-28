import mimetypes

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routes.devices import DevicesRoutes
from api.routes.discovery import DiscoveryRoutes
from api.routes.power import PowerRoutes
from api.routes.shortcuts import ShortcutsRoutes
from api.routes.system import SystemRoutes
from api.security import TokenGuard
from config import Config
from service.errors import DomainError


class ApiFactory:
    def __init__(self, services):
        self.services = services

    def build(self):
        mimetypes.add_type("application/manifest+json", ".webmanifest")
        app = FastAPI(title=Config.APP_NAME, version=Config.VERSION)
        app.add_middleware(
            CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
        )
        guard = TokenGuard(self.services.settings)
        for routes in (
            SystemRoutes(self.services, guard),
            DevicesRoutes(self.services, guard),
            PowerRoutes(self.services, guard),
            DiscoveryRoutes(self.services, guard),
            ShortcutsRoutes(self.services, guard),
        ):
            app.include_router(routes.router)
        app.add_exception_handler(DomainError, self._domain_error)
        self._mount_ui(app)
        return app

    @staticmethod
    async def _domain_error(request, error):
        return JSONResponse({"detail": error.message}, status_code=error.status)

    @staticmethod
    def _mount_ui(app):
        index = Config.WEB_DIR / "index.html"
        app.mount("/static", StaticFiles(directory=Config.WEB_DIR / "static"), name="static")

        @app.get("/", include_in_schema=False)
        def home():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
