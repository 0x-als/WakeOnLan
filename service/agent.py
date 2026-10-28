import json
import urllib.error
import urllib.request

from config import Config
from service.errors import AgentUnavailable


class AgentClient:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, host, port, method, path, token="", payload=None, timeout=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(f"http://{host}:{port}{path}", data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("X-Pulse-Token", token)
        try:
            with self.opener.open(request, timeout=timeout or Config.AGENT_TIMEOUT) as response:
                return response.status, self._parse(response.read())
        except urllib.error.HTTPError as error:
            return error.code, self._parse(error.read())
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise AgentUnavailable(str(error)) from error

    def health(self, host, port):
        try:
            status, body = self.request(host, port, "GET", "/api/health")
        except AgentUnavailable:
            return None
        if status == 200 and isinstance(body, dict) and body.get("app") == Config.APP_ID:
            return body
        return None

    @staticmethod
    def _parse(raw):
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return {}
