class DomainError(Exception):
    status = 400

    def __init__(self, message, status=None):
        super().__init__(message)
        self.message = message
        if status is not None:
            self.status = status


class DeviceNotFound(DomainError):
    status = 404


class DuplicateDevice(DomainError):
    status = 409


class ActionError(DomainError):
    status = 409


class PowerError(DomainError):
    status = 500


class AgentUnavailable(DomainError):
    status = 504
