from service.errors import ActionError, AgentUnavailable


class DeviceActions:
    def __init__(self, settings, identity, wake, power, agent):
        self.settings = settings
        self.identity = identity
        self.wake_service = wake
        self.power = power
        self.agent = agent

    def wake(self, device):
        if self.identity.is_self(device):
            raise ActionError("Этот компьютер уже включён: сервер работает на нём", 409)
        try:
            return self.wake_service.wake(device.mac, device.broadcast, device.wol_port)
        except OSError as error:
            raise ActionError(f"Не удалось отправить Magic Packet: {error}", 500) from error

    def shutdown(self, device, delay, force=False):
        if self.identity.is_self(device):
            self.power.shutdown(delay, force)
            return
        self._forward(device, "/api/shutdown", {"delay": delay, "force": force})

    def cancel(self, device):
        if self.identity.is_self(device):
            self.power.cancel()
            return
        self._forward(device, "/api/shutdown/cancel", {})

    def _forward(self, device, path, payload):
        host = (device.host or "").strip()
        if not (device.agent and host):
            raise ActionError(
                "На этом компьютере не настроен сервер Pulse: удалённое выключение недоступно",
                409,
            )
        token = device.token or self.settings.token
        try:
            status, body = self.agent.request(
                host, device.port, "POST", path, token=token, payload=payload, timeout=4
            )
        except AgentUnavailable as error:
            raise ActionError(
                "Компьютер не отвечает: он выключен или Pulse на нём не запущен", 504
            ) from error
        if status == 401:
            raise ActionError(
                "Компьютер отклонил ключ доступа. Задайте одинаковый ключ на всех ПК", 502
            )
        if status >= 400:
            detail = body.get("detail") if isinstance(body, dict) else None
            raise ActionError(str(detail or "Компьютер вернул ошибку"), 502)

