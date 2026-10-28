import secrets

from fastapi import HTTPException, Request


class TokenGuard:
    LOOPBACK = ("127.0.0.1", "::1", "localhost")

    def __init__(self, settings):
        self.settings = settings

    def __call__(self, request: Request):
        client = request.client.host if request.client else ""
        if client in self.LOOPBACK:
            return
        supplied = self._extract(request)
        expected = self.settings.token
        if not supplied or not secrets.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="Неверный ключ доступа")

    @staticmethod
    def _extract(request):
        header = request.headers.get("x-pulse-token")
        if header:
            return header.strip()
        bearer = request.headers.get("authorization", "")
        if bearer.lower().startswith("bearer "):
            return bearer[7:].strip()
        return (request.query_params.get("token") or "").strip()
