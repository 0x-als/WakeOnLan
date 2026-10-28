import argparse
import logging
import os
import subprocess
import sys
import time
import webbrowser

from config import Config
from service.container import Services
from service.firewall import FirewallManager
from service.instance import InstanceGuard
from service.network import hidden_window_flags
from service.settings import Settings

SCRIPT = os.path.abspath(__file__)


class Application:
    def __init__(self, argv):
        self.args = self._parse(argv)
        self.guard = InstanceGuard()
        self.settings = None
        self.services = None
        self.runner = None
        self.tray = None

    @staticmethod
    def _parse(argv):
        parser = argparse.ArgumentParser(prog="pulse", description="Pulse: сервер удалённого управления ПК")
        parser.add_argument("--background", action="store_true", help="запуск в фоне (без открытия браузера)")
        parser.add_argument("--no-tray", action="store_true", help="не показывать значок в трее")
        parser.add_argument("--port", type=int, help="порт сервера (сохраняется в настройках)")
        parser.add_argument("--install", action="store_true", help="включить автозапуск и правила брандмауэра")
        parser.add_argument("--uninstall", action="store_true", help="убрать автозапуск и правила брандмауэра")
        parser.add_argument("--firewall", action="store_true", help="добавить правила брандмауэра (нужны права администратора)")
        parser.add_argument("--firewall-remove", action="store_true", help="удалить правила брандмауэра")
        parser.add_argument("--token", action="store_true", help="показать ключ доступа и адреса, затем выйти")
        return parser.parse_args(argv[1:])

    def _prepare_environment(self):
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w")
        Config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        handlers = [logging.FileHandler(Config.LOG_FILE, encoding="utf-8")]
        if sys.stdout.isatty():
            handlers.append(logging.StreamHandler(sys.stdout))
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers
        )
        sys.excepthook = lambda kind, value, trace: logging.error(
            "Необработанная ошибка", exc_info=(kind, value, trace)
        )

    def run(self):
        self._prepare_environment()
        args = self.args
        if args.firewall or args.firewall_remove:
            return self._firewall(remove=args.firewall_remove)
        if args.install:
            return self._install()
        if args.uninstall:
            return self._uninstall()
        if args.token:
            return self._show_token()
        return self._serve()

    def _load_settings(self):
        settings = Settings.load()
        if self.args.port:
            settings.port = self.args.port
            settings.save()
        return settings

    def _firewall(self, remove):
        settings = self._load_settings()
        manager = FirewallManager(SCRIPT)
        if not manager.is_admin():
            print("Нужны права администратора.")
            return 1
        ok = manager.remove_rules(settings.port) if remove else manager.add_rules(settings.port)
        print("Готово." if ok else "Не удалось изменить правила брандмауэра.")
        time.sleep(2)
        return 0 if ok else 1

    def _install(self):
        settings = self._load_settings()
        services = Services(settings, SCRIPT)
        manager = FirewallManager(SCRIPT)
        if services.autostart.set_enabled(True):
            print("Автозапуск включён.")
        settings.autostart_initialized = True
        settings.save()
        if manager.is_admin():
            manager.add_rules(settings.port)
            print("Правила брандмауэра добавлены.")
        elif manager.elevate("--firewall"):
            print("Подтвердите запрос Windows (UAC), чтобы добавить правила брандмауэра.")
        else:
            print("Не удалось запросить права администратора. Запустите: python main.py --firewall от имени администратора.")
        return 0

    def _uninstall(self):
        settings = self._load_settings()
        services = Services(settings, SCRIPT)
        services.autostart.set_enabled(False)
        manager = FirewallManager(SCRIPT)
        if manager.is_admin():
            manager.remove_rules(settings.port)
        else:
            manager.elevate("--firewall-remove")
        print("Автозапуск отключён.")
        return 0

    def _show_token(self):
        settings = self._load_settings()
        services = Services(settings, SCRIPT)
        print(f"Ключ доступа: {settings.token}")
        for url in services.identity.urls():
            print(f"Ссылка для телефона: {url}/?token={settings.token}")
        return 0

    def _local_url(self):
        return f"http://127.0.0.1:{self.settings.port}/?token={self.settings.token}"

    def _phone_url(self):
        urls = self.services.identity.urls()
        base = urls[0] if urls else f"http://127.0.0.1:{self.settings.port}"
        return f"{base}/?token={self.settings.token}"

    def open_panel(self):
        webbrowser.open(self._local_url())

    def copy_phone_link(self):
        if not Config.IS_WIN:
            return
        try:
            subprocess.run(
                ["clip"], input=self._phone_url().encode("ascii", errors="ignore"),
                timeout=5, creationflags=hidden_window_flags(),
            )
        except Exception:
            logging.exception("Не удалось скопировать ссылку")

    def quit(self):
        if self.tray:
            self.tray.stop()
        if self.runner:
            self.runner.server.should_exit = True

    def _first_run_autostart(self):
        if self.settings.autostart_initialized or not self.services.autostart.supported():
            return
        self.services.autostart.set_enabled(True)
        self.settings.autostart_initialized = True
        self.settings.save()

    def _serve(self):
        from api.app import ApiFactory
        from service.runner import ServerRunner
        from service.tray import TrayService

        if not self.guard.acquire():
            self.guard.ping()
            return 0
        self.settings = self._load_settings()
        self.services = Services(self.settings, SCRIPT)
        self._first_run_autostart()
        self.services.responder.start()

        app = ApiFactory(self.services).build()
        self.runner = ServerRunner(app, Config.HOST, self.settings.port)
        if not self.runner.start():
            logging.error("Не удалось запустить сервер на порту %s (порт занят?)", self.settings.port)
            print(f"Не удалось запустить сервер на порту {self.settings.port}. Возможно, порт занят.")
            self.services.responder.stop()
            return 1

        self.guard.serve(self.open_panel)
        self._announce()
        if not self.args.background:
            self.open_panel()

        try:
            if TrayService.available and not self.args.no_tray:
                self.tray = TrayService(
                    self.open_panel, self.copy_phone_link,
                    self.services.autostart.is_enabled, self.services.autostart.set_enabled,
                    self.services.autostart.supported(), self.quit,
                )
                if not self.tray.run():
                    self.runner.wait()
            else:
                self.runner.wait()
        except KeyboardInterrupt:
            pass
        finally:
            self.services.responder.stop()
            self.runner.stop()
            self.guard.release()
        return 0

    def _announce(self):
        logging.info("%s %s запущен на порту %s", Config.APP_NAME, Config.VERSION, self.settings.port)
        print(f"{Config.APP_NAME} запущен. Ключ доступа: {self.settings.token}")
        for url in self.services.identity.urls():
            print(f"  Адрес: {url}   Ссылка для телефона: {url}/?token={self.settings.token}")


if __name__ == "__main__":
    sys.exit(Application(sys.argv).run())
