import logging
import subprocess

from config import Config
from service.errors import PowerError
from service.network import hidden_window_flags


class PowerService:
    def shutdown(self, delay=None, force=False):
        seconds = Config.SHUTDOWN_DELAY if delay is None else int(delay)
        command = [
            "shutdown", "/s", "/t", str(seconds),
            "/c", f"{Config.APP_NAME}: удалённое выключение",
        ]
        if force:
            command.append("/f")
        self._run(command, ok_codes=(0, 1190))

    def cancel(self):
        self._run(["shutdown", "/a"], ok_codes=(0, 1116))

    def _run(self, command, ok_codes):
        if Config.DRY_RUN:
            logging.info("DRY RUN: %s", " ".join(command))
            return
        if not Config.IS_WIN:
            raise PowerError("Выключение поддерживается только в Windows", 501)
        try:
            result = subprocess.run(
                command, capture_output=True, timeout=15, creationflags=hidden_window_flags()
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise PowerError(f"Не удалось выполнить команду: {error}") from error
        if result.returncode not in ok_codes:
            details = (result.stderr or result.stdout).decode("cp866", errors="ignore").strip()
            raise PowerError(details or f"Команда завершилась с кодом {result.returncode}")
