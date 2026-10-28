from fastapi import APIRouter, Depends


class DiscoveryRoutes:
    def __init__(self, services, guard):
        self.services = services
        self.router = APIRouter(
            prefix="/api/discovery", tags=["discovery"], dependencies=[Depends(guard)]
        )
        self.router.add_api_route("/scan", self.scan, methods=["POST"])

    def scan(self):
        devices, networks = self.services.scanner.scan()
        return {"devices": devices, "networks": networks}
