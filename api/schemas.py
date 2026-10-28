import ipaddress

from pydantic import BaseModel, Field, field_validator

from config import Config
from service.mac import Mac


def _check_broadcast(value):
    value = (value or "").strip() or Config.DEFAULT_BROADCAST
    try:
        ipaddress.IPv4Address(value)
    except ValueError as error:
        raise ValueError("Broadcast-адрес должен быть IPv4, например 192.168.1.255") from error
    return value


class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    mac: str
    host: str = Field(default="", max_length=120)
    port: int = Field(default=Config.PORT, ge=1, le=65535)
    broadcast: str = Config.DEFAULT_BROADCAST
    wol_port: int = Field(default=Config.DEFAULT_WOL_PORT, ge=1, le=65535)
    agent: bool = False
    token: str = Field(default="", max_length=64)

    @field_validator("name")
    @classmethod
    def _name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Укажите название")
        return value

    @field_validator("mac")
    @classmethod
    def _mac(cls, value):
        return Mac.normalize(value)

    @field_validator("host", "token")
    @classmethod
    def _strip(cls, value):
        return value.strip()

    @field_validator("broadcast")
    @classmethod
    def _broadcast(cls, value):
        return _check_broadcast(value)


class WakeIn(BaseModel):
    mac: str
    broadcast: str = Config.DEFAULT_BROADCAST
    port: int = Field(default=Config.DEFAULT_WOL_PORT, ge=1, le=65535)

    @field_validator("mac")
    @classmethod
    def _mac(cls, value):
        return Mac.normalize(value)

    @field_validator("broadcast")
    @classmethod
    def _broadcast(cls, value):
        return _check_broadcast(value)


class ShutdownIn(BaseModel):
    delay: int = Field(default=Config.SHUTDOWN_DELAY, ge=0, le=600)
    force: bool = False


class AutostartIn(BaseModel):
    enabled: bool
