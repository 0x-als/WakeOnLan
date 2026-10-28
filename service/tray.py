import logging

from PIL import Image, ImageDraw, ImageFilter

from config import Config

try:
    import pystray
except Exception:
    pystray = None


class TrayService:
    available = pystray is not None

    def __init__(self, on_open, on_copy, is_autostart, set_autostart, autostart_supported, on_quit):
        self.on_open = on_open
        self.on_copy = on_copy
        self.is_autostart = is_autostart
        self.set_autostart = set_autostart
        self.autostart_supported = autostart_supported
        self.on_quit = on_quit
        self.icon = None

    @staticmethod
    def render_icon():
        scale = 4
        size = 64 * scale
        center = size / 2
        glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        radius = 22 * scale
        ImageDraw.Draw(glow).ellipse(
            [center - radius, center - radius, center + radius, center + radius],
            fill=(52, 211, 153, 140),
        )
        glow = glow.filter(ImageFilter.GaussianBlur(5 * scale))
        shape = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(shape)
        for radius, fill in ((24, "#34d399"), (17, "#0c0d10"), (8, "#34d399")):
            r = radius * scale
            draw.ellipse([center - r, center - r, center + r, center + r], fill=fill)
        resample = getattr(Image, "Resampling", Image).LANCZOS
        merged = Image.alpha_composite(glow, shape)
        return merged.resize((64, 64), resample)

    def _build_menu(self):
        items = [
            pystray.MenuItem("Открыть панель", lambda icon, item: self.on_open(), default=True),
            pystray.MenuItem("Скопировать ссылку для телефона", lambda icon, item: self.on_copy()),
        ]
        if self.autostart_supported:
            items.append(
                pystray.MenuItem(
                    "Запускать вместе с Windows",
                    lambda icon, item: self.set_autostart(not self.is_autostart()),
                    checked=lambda item: self.is_autostart(),
                )
            )
        items += [pystray.Menu.SEPARATOR, pystray.MenuItem("Выход", lambda icon, item: self.on_quit())]
        return pystray.Menu(*items)

    def run(self):
        try:
            self.icon = pystray.Icon(
                Config.APP_NAME, self.render_icon(), f"{Config.APP_NAME} — сервер работает",
                self._build_menu(),
            )
            self.icon.run()
            return True
        except Exception:
            logging.exception("Не удалось запустить иконку в трее")
            self.icon = None
            return False

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
