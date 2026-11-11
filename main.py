"""
WoL Shutdown — выключает ПК при получении магического пакета Wake-on-LAN.

Зависимости (для значка в трее):
    pip install pystray pillow

Журнал перехваченных пакетов в консоли:
    python wol_shutdown.py             (если запускать из cmd/PowerShell)
    wol_shutdown.exe --console         (открывает окно консоли даже у сборки --noconsole)

Сборка в .exe:
    pip install pyinstaller
    pyinstaller --noconsole --onefile --hidden-import pystray._win32 wol_shutdown.py
"""
import json
import os
import queue
import select
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

try:
    import winreg
except ImportError:  # не Windows
    winreg = None

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:  # без трея приложение сворачивается на панель задач
    pystray = None

APP_NAME = "WoLShutdown"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LOCK_PORT = 48213          # защита от запуска второй копии
COOLDOWN = 30              # сек. между двумя срабатываниями
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

DEFAULTS = {"mac": "", "ports": [9, 7], "delay": 10, "grace": 90, "autostart": False}


# ---------- вывод в консоль ----------
def log(msg):
    """Печатает строку с временем. Если консоли нет (--noconsole), ничего не делает."""
    try:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
    except Exception:
        pass


def attach_console():
    """Открывает окно консоли (нужно для .exe, собранного с --noconsole)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.AllocConsole():       # 0, если консоль уже есть
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleTitleW("WoL Shutdown — журнал")
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            sys.stderr = sys.stdout
    except Exception:
        pass

# ---------- цвета ----------
BG = "#f6f7f9"
CARD = "#ffffff"
TEXT = "#1f2328"
MUTED = "#6b7280"
ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
BORDER = "#dfe3e8"
OK, WARN, ERR = "#16a34a", "#d97706", "#dc2626"


# ---------- настройки ----------
def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ---------- автозапуск ----------
def launch_command():
    if getattr(sys, "frozen", False):          # собранный .exe
        return f'"{sys.executable}" --minimized'
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    return f'"{exe}" "{os.path.abspath(__file__)}" --minimized'


def set_autostart(enabled):
    if winreg is None:
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def is_autostart_enabled():
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


# ---------- магический пакет ----------
def parse_mac(text):
    clean = "".join(c for c in text if c not in ":-. ").lower()
    if len(clean) != 12 or any(c not in "0123456789abcdef" for c in clean):
        raise ValueError("MAC-адрес должен состоять из 12 шестнадцатеричных цифр")
    return bytes.fromhex(clean)


def format_mac(raw):
    return ":".join(f"{b:02X}" for b in raw)


def parse_ports(text):
    ports = []
    for part in text.replace(";", ",").replace(" ", ",").split(","):
        if part:
            p = int(part)
            if not 1 <= p <= 65535:
                raise ValueError
            if p not in ports:
                ports.append(p)
    if not ports:
        raise ValueError
    return ports


def is_magic_for(data, mac_bytes):
    return len(data) >= 102 and data[:6] == b"\xff" * 6 and data[6:102] == mac_bytes * 16


def is_magic_packet(data):
    """Магический пакет для любого MAC (чтобы заметить пакеты с чужим адресом)."""
    return len(data) >= 102 and data[:6] == b"\xff" * 6 and data[6:12] * 16 == data[6:102]


class Listener(threading.Thread):
    def __init__(self, mac_bytes, ports, out_queue):
        super().__init__(daemon=True)
        self.mac, self.ports, self.q = mac_bytes, ports, out_queue
        self.stop_event = threading.Event()

    def run(self):
        socks = []
        try:
            for p in self.ports:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", p))
                socks.append(s)
        except OSError as e:
            for s in socks:
                s.close()
            self.q.put(("error", f"Не удалось открыть порт: {e.strerror or e}"))
            return
        self.q.put(("listening", None))
        while not self.stop_event.is_set():
            try:
                ready, _, _ = select.select(socks, [], [], 0.5)
            except OSError:
                break
            for s in ready:
                try:
                    data, addr = s.recvfrom(1024)
                except OSError:
                    continue
                port = s.getsockname()[1]
                if is_magic_for(data, self.mac):
                    self.q.put(("packet", (addr[0], port)))
                elif is_magic_packet(data):
                    self.q.put(("foreign", (addr[0], port, format_mac(data[6:12]))))
        for s in socks:
            s.close()

    def stop(self):
        self.stop_event.set()


# ---------- значок трея ----------
def make_tray_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=14, fill=ACCENT)
    d.arc((17, 17, 47, 47), start=-50, end=230, fill="white", width=5)
    d.line((32, 12, 32, 31), fill="white", width=5)
    return img


# ---------- интерфейс ----------
class App:
    def __init__(self, root, minimized):
        self.root = root
        if minimized and pystray is not None:
            self.root.withdraw()  # сразу прячем, чтобы окно не мигало при автозапуске
        self.cfg = load_config()
        self.cfg["autostart"] = is_autostart_enabled()
        self.q = queue.Queue()
        self.listener = None
        self.tray = None
        self.started = time.time()
        self.last_trigger = 0
        self.pending_until = None

        self.build_ui()
        self.setup_tray()
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)  # крестик прячет в трей
        self.root.bind("<Unmap>", self.on_unmap)  # кнопка «свернуть» тоже прячет в трей
        self.start_listener()
        self.root.after(200, self.poll)
        if minimized:
            self.root.after(50, self.hide_window)

    # --- окно ---
    def hide_window(self):
        if self.tray:
            self.root.withdraw()
        else:
            self.root.iconify()

    def on_unmap(self, event):
        # Обычное сворачивание (кнопка «_») оставляет окно на панели задач.
        # Если трей доступен, превращаем его в полное скрытие.
        if event.widget is self.root and self.tray and self.root.state() == "iconic":
            self.root.after_idle(self.root.withdraw)

    def show_window(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def setup_tray(self):
        if pystray is None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Открыть", lambda icon, item: self.q.put(("show", None)), default=True),
            pystray.MenuItem("Выход", lambda icon, item: self.q.put(("quit", None))),
        )
        self.tray = pystray.Icon(APP_NAME, make_tray_image(), "WoL Shutdown", menu)
        self.tray.run_detached()

    def build_ui(self):
        r = self.root
        r.title("WoL Shutdown")
        r.configure(bg=BG)
        r.resizable(False, False)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background=BG, foreground=TEXT)
        style.configure("TLabel", background=CARD, foreground=TEXT)
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=BG, font=("Segoe UI Semibold", 16))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("TEntry", fieldbackground=CARD, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER, padding=6)
        style.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)])
        style.configure("TSpinbox", fieldbackground=CARD, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER, arrowsize=12, padding=5)
        style.configure("TCheckbutton", background=CARD, foreground=TEXT)
        style.map("TCheckbutton", background=[("active", CARD)])
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                        borderwidth=0, padding=(18, 8), font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER)])
        style.configure("Ghost.TButton", background=BG, foreground=MUTED,
                        borderwidth=0, padding=(12, 8))
        style.map("Ghost.TButton", foreground=[("active", TEXT)], background=[("active", BG)])
        style.configure("Danger.TButton", background=ERR, foreground="white",
                        borderwidth=0, padding=(12, 6))
        style.map("Danger.TButton", background=[("active", "#b91c1c")])

        outer = tk.Frame(r, bg=BG, padx=24, pady=22)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="WoL Shutdown", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Выключает этот ПК, когда приходит магический пакет",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 14))

        card = tk.Frame(outer, bg=CARD, highlightbackground=BORDER, highlightthickness=1,
                        padx=20, pady=18)
        card.pack(fill="x")

        self.mac_var = tk.StringVar(value=self.cfg["mac"])
        self.ports_var = tk.StringVar(value=", ".join(map(str, self.cfg["ports"])))
        self.delay_var = tk.StringVar(value=str(int(self.cfg["delay"])))
        self.grace_var = tk.StringVar(value=str(int(self.cfg["grace"])))
        self.auto_var = tk.BooleanVar(value=self.cfg["autostart"])

        self.field(card, "MAC-адрес этого ПК",
                   "Как в приложении на телефоне, например AA:BB:CC:DD:EE:FF",
                   lambda p: ttk.Entry(p, textvariable=self.mac_var, width=34))
        self.field(card, "UDP-порты", "Через запятую; обычно 9 и 7",
                   lambda p: ttk.Entry(p, textvariable=self.ports_var, width=34))

        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x")
        left = tk.Frame(row, bg=CARD)
        left.pack(side="left", fill="x", expand=True)
        right = tk.Frame(row, bg=CARD)
        right.pack(side="left", fill="x", expand=True, padx=(16, 0))
        self.field(left, "Выключить через, сек", "0 — сразу",
                   lambda p: ttk.Spinbox(p, from_=0, to=3600, textvariable=self.delay_var, width=10))
        self.field(right, "Игнорировать после старта, сек", "Защита от повторных пакетов",
                   lambda p: ttk.Spinbox(p, from_=0, to=600, textvariable=self.grace_var, width=10))

        ttk.Checkbutton(card, text="Запускать вместе с Windows (в трее)",
                        variable=self.auto_var).pack(anchor="w", pady=(2, 0))

        btns = tk.Frame(outer, bg=BG)
        btns.pack(fill="x", pady=(16, 0))
        ttk.Button(btns, text="Сохранить", style="Accent.TButton",
                   command=self.on_save).pack(side="left")
        ttk.Button(btns, text="Выйти", style="Ghost.TButton",
                   command=self.on_quit).pack(side="left", padx=(8, 0))
        self.cancel_btn = ttk.Button(btns, text="Отменить выключение", style="Danger.TButton",
                                     command=self.cancel_shutdown)

        status = tk.Frame(outer, bg=BG)
        status.pack(fill="x", pady=(14, 0))
        self.dot = tk.Canvas(status, width=10, height=10, bg=BG, highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 8))
        self.dot_id = self.dot.create_oval(1, 1, 9, 9, fill=MUTED, outline="")
        self.status_var = tk.StringVar(value="Не настроено")
        ttk.Label(status, textvariable=self.status_var, style="Status.TLabel",
                  background=BG).pack(side="left")

    def field(self, parent, title, hint, make_widget):
        """Виджет создаётся ВНУТРИ контейнера box, иначе box перекрывает поле ввода."""
        box = tk.Frame(parent, bg=CARD)
        box.pack(fill="x", pady=(0, 14))
        ttk.Label(box, text=title).pack(anchor="w", pady=(0, 4))
        widget = make_widget(box)
        widget.pack(anchor="w", fill="x")
        ttk.Label(box, text=hint, style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        return widget

    def set_status(self, text, color):
        self.status_var.set(text)
        self.dot.itemconfig(self.dot_id, fill=color)

    # --- логика ---
    def on_save(self):
        try:
            mac = parse_mac(self.mac_var.get())
        except ValueError as e:
            self.set_status(str(e), ERR)
            return
        try:
            ports = parse_ports(self.ports_var.get())
        except ValueError:
            self.set_status("Порты: числа от 1 до 65535 через запятую", ERR)
            return
        try:
            delay = max(0, min(3600, int(self.delay_var.get())))
            grace = max(0, min(600, int(self.grace_var.get())))
        except ValueError:
            self.set_status("Время должно быть целым числом секунд", ERR)
            return

        self.cfg.update(mac=format_mac(mac), ports=ports, delay=delay,
                        grace=grace, autostart=bool(self.auto_var.get()))
        self.mac_var.set(self.cfg["mac"])
        self.ports_var.set(", ".join(map(str, ports)))
        self.delay_var.set(str(delay))
        self.grace_var.set(str(grace))
        try:
            save_config(self.cfg)
            set_autostart(self.cfg["autostart"])
        except OSError as e:
            self.set_status(f"Не удалось сохранить: {e}", ERR)
            log(f"ОШИБКА сохранения: {e}")
            return
        log(f"Настройки сохранены: MAC {self.cfg['mac']}, порты {ports}, "
            f"задержка {delay} с, игнор после старта {grace} с, "
            f"автозапуск {'вкл' if self.cfg['autostart'] else 'выкл'}")
        self.start_listener()

    def start_listener(self):
        if self.listener:
            self.listener.stop()
            self.listener = None
        try:
            mac = parse_mac(self.cfg["mac"])
        except ValueError:
            self.set_status("Укажите MAC-адрес и нажмите «Сохранить»", WARN)
            return
        self.listener = Listener(mac, self.cfg["ports"], self.q)
        self.listener.start()

    def poll(self):
        try:
            while True:
                kind, value = self.q.get_nowait()
                if kind == "listening":
                    ports = ", ".join(map(str, self.cfg["ports"]))
                    self.set_status(f"Слушаю порты {ports}", OK)
                    log(f"Слушаю UDP-порты {ports}, MAC {self.cfg['mac']}")
                elif kind == "error":
                    self.set_status(value, ERR)
                    log(f"ОШИБКА: {value}")
                elif kind == "packet":
                    self.on_packet(*value)
                elif kind == "foreign":
                    ip, port, mac = value
                    log(f"Магический пакет для ДРУГОГО MAC {mac} от {ip}, порт {port} (игнорирую)")
                elif kind == "show":
                    self.show_window()
                elif kind == "quit":
                    self.on_quit()
                    return
        except queue.Empty:
            pass
        if self.pending_until:
            left = int(self.pending_until - time.time() + 0.99)
            if left > 0:
                self.set_status(f"Выключение через {left} с", WARN)
            else:
                self.pending_until = None
        self.root.after(250, self.poll)

    def on_packet(self, ip, port):
        now = time.time()
        src = f"от {ip}, порт {port}"
        left_grace = self.cfg["grace"] - (now - self.started)
        if left_grace > 0:
            log(f"Магический пакет {src} — проигнорирован (период после старта, ещё {int(left_grace)} с)")
            return
        if now - self.last_trigger < COOLDOWN:
            log(f"Магический пакет {src} — проигнорирован (повтор, пауза {COOLDOWN} с)")
            return
        self.last_trigger = now
        delay = int(self.cfg["delay"])
        log(f"Магический пакет {src} — выключаю ПК через {delay} с")
        try:
            subprocess.run(["shutdown", "/s", "/t", str(delay)], creationflags=NO_WINDOW)
        except OSError as e:
            self.set_status(f"Ошибка shutdown: {e}", ERR)
            log(f"ОШИБКА shutdown: {e}")
            return
        if delay > 0:
            self.pending_until = now + delay
            self.cancel_btn.pack(side="right")
            if self.tray:
                try:
                    self.tray.notify(f"Выключение через {delay} с. Отмена: откройте окно приложения.",
                                     "WoL Shutdown")
                except Exception:
                    pass
        self.set_status(f"Пакет от {ip}. Выключение через {delay} с", WARN)

    def cancel_shutdown(self):
        subprocess.run(["shutdown", "/a"], creationflags=NO_WINDOW)
        self.pending_until = None
        self.cancel_btn.pack_forget()
        self.set_status("Выключение отменено", OK)
        log("Выключение отменено пользователем")

    def on_quit(self):
        if self.listener:
            self.listener.stop()
        if self.tray:
            self.tray.stop()
        self.root.destroy()


def main():
    # защита от второй копии
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        return

    if "--console" in sys.argv:
        attach_console()

    root = tk.Tk()
    App(root, minimized="--minimized" in sys.argv)
    root.mainloop()


if __name__ == "__main__":
    main()