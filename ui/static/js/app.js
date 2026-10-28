class PulseApp {
  constructor(root) {
    this.root = root;
    this.native = Native.available;
    this.token = Store.get("token", "");
    this.serverUrl = this.native ? Store.get("serverUrl", "") : window.location.origin;
    this.devices = Store.get("devices", []);
    this.selectedId = Store.get("selected", null);
    this.server = null;
    this.api = null;
    this.online = false;
    this.pending = {};
    this.refreshing = false;
    this.pollTimer = null;
    this.toast = new Toast(document.getElementById("toasts"));
    this.gate = new GateView(this);
    this.home = new HomeView(this);
    this.view = null;
  }

  isLocalHost() {
    return ["localhost", "127.0.0.1", "[::1]"].indexOf(window.location.hostname) !== -1;
  }

  isStandalone() {
    return window.navigator.standalone === true ||
      (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
  }

  readUrlToken() {
    if (this.native) {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (!token) {
      return;
    }
    this.token = token.trim();
    Store.set("token", this.token);
    if (this.isStandalone()) {
      window.history.replaceState(null, "", window.location.pathname);
    }
  }

  configured() {
    if (this.native) {
      return Boolean(this.serverUrl && this.token);
    }
    return Boolean(this.token) || this.isLocalHost();
  }

  buildApi() {
    this.api = new ApiClient(this.serverUrl, this.token);
  }

  async start() {
    this.readUrlToken();
    this.root.addEventListener("click", (event) => {
      if (this.view && this.view.handle) {
        this.view.handle(event);
      }
    });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && this.view === this.home) {
        this.refresh();
      }
    });
    window.__pulseBack = () => this.back();
    if (!this.configured()) {
      this.showGate("");
      return;
    }
    this.buildApi();
    this.showHome();
    await this.refresh();
    this.startPolling();
  }

  showGate(message) {
    this.stopPolling();
    this.view = this.gate;
    this.gate.render(message);
  }

  showHome() {
    this.view = this.home;
    this.home.render(true);
  }

  startPolling() {
    this.stopPolling();
    this.pollTimer = setInterval(() => {
      if (document.visibilityState === "visible" && this.view === this.home) {
        this.refresh();
      }
    }, 5000);
  }

  stopPolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  fastPoll(seconds, done) {
    const end = Date.now() + seconds * 1000;
    const tick = async () => {
      if (this.view !== this.home) {
        return;
      }
      await this.refresh();
      if (Date.now() < end && !(done && done())) {
        setTimeout(tick, 2500);
      }
    };
    setTimeout(tick, 2500);
  }

  async connect(url, token) {
    const cleanToken = (token || "").trim();
    let base = this.serverUrl;
    if (this.native) {
      base = ApiClient.normalizeUrl(url);
      if (!base) {
        throw new Error("Укажите адрес сервера");
      }
    }
    if (!cleanToken && !(this.isLocalHost() && !this.native)) {
      throw new Error("Введите ключ доступа");
    }
    const api = new ApiClient(base, cleanToken);
    const info = await api.info();
    this.serverUrl = base;
    this.token = cleanToken;
    this.api = api;
    this.server = info;
    Store.set("token", cleanToken);
    if (this.native) {
      Store.set("serverUrl", base);
    }
    this.showHome();
    await this.refresh(true);
    this.startPolling();
  }

  logout(message) {
    this.token = "";
    Store.remove("token");
    this.api = null;
    this.server = null;
    this.online = false;
    this.showGate(message || "");
  }

  selected() {
    return this.devices.find((device) => device.id === this.selectedId) || this.devices[0] || null;
  }

  select(id) {
    this.selectedId = id;
    Store.set("selected", id);
    this.home.render();
  }

  async refresh(force) {
    if (this.refreshing || !this.api) {
      return;
    }
    this.refreshing = true;
    try {
      if (!this.server || force) {
        this.server = await this.api.info();
      }
      this.devices = await this.api.devices();
      this.online = true;
      Store.set("devices", this.devices);
      if (!this.devices.some((device) => device.id === this.selectedId)) {
        this.selectedId = this.devices.length ? this.devices[0].id : null;
        Store.set("selected", this.selectedId);
      }
    } catch (error) {
      if (error.status === 401) {
        this.refreshing = false;
        this.logout("Неверный ключ доступа");
        return;
      }
      this.online = false;
    }
    this.refreshing = false;
    if (this.view === this.home) {
      this.home.render();
    }
  }

  setPending(id, value) {
    if (value) {
      this.pending[id] = value;
    } else {
      delete this.pending[id];
    }
    this.home.render();
  }

  onPower() {
    const device = this.selected();
    if (!device) {
      return;
    }
    if (this.online && device.online === true && !device.is_self) {
      this.shutdownSelected();
    } else if (!device.is_self) {
      this.wakeSelected();
    }
  }

  async wakeSelected() {
    const device = this.selected();
    if (!device || this.pending[device.id]) {
      return;
    }
    this.setPending(device.id, "wake");
    let sent = false;
    let problem = "";
    if (this.native) {
      try {
        await Native.call("wake", device.mac, device.broadcast || "255.255.255.255", device.wol_port || 9);
        sent = true;
      } catch (error) {
        problem = error.message;
      }
    }
    if (this.online) {
      try {
        await this.api.wake(device.id);
        sent = true;
      } catch (error) {
        problem = error.message;
      }
    }
    this.setPending(device.id, null);
    if (sent) {
      this.toast.show("Magic Packet отправлен. ПК включится через 10–60 секунд");
      this.fastPoll(90, () => {
        const current = this.devices.find((item) => item.id === device.id);
        return current && current.online === true;
      });
    } else {
      this.toast.error(problem || "Не удалось отправить пакет");
    }
  }

  async shutdownSelected() {
    const device = this.selected();
    if (!device || this.pending[device.id]) {
      return;
    }
    const ok = await Dialog.confirm({
      title: "Выключить «" + device.name + "»?",
      text: "ПК выключится через 10 секунд. Выключение можно отменить.",
      confirm: "Выключить",
      danger: true
    });
    if (!ok) {
      return;
    }
    this.setPending(device.id, "shutdown");
    try {
      await this.api.shutdown(device.id, 10, false);
      this.setPending(device.id, null);
      this.toast.show("Выключение через 10 секунд", {
        action: "Отменить",
        duration: 10000,
        onAction: () => this.cancelShutdown(device)
      });
      this.fastPoll(60, () => {
        const current = this.devices.find((item) => item.id === device.id);
        return current && current.online === false;
      });
    } catch (error) {
      this.setPending(device.id, null);
      this.toast.error(error.message);
    }
  }

  async cancelShutdown(device) {
    try {
      await this.api.cancel(device.id);
      this.toast.show("Выключение отменено");
    } catch (error) {
      this.toast.error(error.message);
    }
  }

  openSettings() {
    new SettingsSheet(this).open();
  }

  openDevice(id) {
    const device = id ? this.devices.find((item) => item.id === id) : null;
    if (id && !device) {
      return;
    }
    if (!this.online) {
      this.toast.error("Нет связи с сервером");
      return;
    }
    new DeviceSheet(this, device).open();
  }

  openDiscovery() {
    if (!this.online) {
      this.toast.error("Нет связи с сервером");
      return;
    }
    new DiscoverySheet(this).open();
  }

  async afterDeviceChanged(device) {
    if (device && (!this.selectedId || !this.devices.length)) {
      this.selectedId = device.id;
      Store.set("selected", device.id);
    }
    await this.refresh(true);
  }

  baseUrl() {
    const urls = this.server && this.server.urls;
    return urls && urls.length ? urls[0] : this.serverUrl;
  }

  tokenValue() {
    return this.token || (this.server && this.server.token) || "";
  }

  shortcutUrl(kind, id) {
    return this.baseUrl() + "/api/shortcuts/" + kind + "/" + id + "?token=" + encodeURIComponent(this.tokenValue());
  }

  phoneLink() {
    return this.baseUrl() + "/?token=" + encodeURIComponent(this.tokenValue());
  }

  back() {
    if (Dialog.current) {
      Dialog.current();
      return true;
    }
    if (Sheet.current) {
      Sheet.current.close();
      return true;
    }
    return false;
  }
}

new PulseApp(document.getElementById("app")).start();
