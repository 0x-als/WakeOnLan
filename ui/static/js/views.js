class Format {
  static dot(app, device) {
    if (!app.online) {
      return "unk";
    }
    return device.online === true ? "ok" : "unk";
  }

  static sub(device) {
    return Dom.escape((device.host || "IP не указан") + " · " + device.mac);
  }

  static badges(device) {
    return (device.is_self ? '<em class="badge">Этот ПК</em>' : "") +
      (device.agent ? '<em class="badge ok">Pulse</em>' : "");
  }
}

class GateView {
  constructor(app) {
    this.app = app;
    this.found = [];
  }

  template(message) {
    const app = this.app;
    const server = app.native
      ? '<label class="field"><span>Адрес сервера</span>' +
        '<input id="gate-url" type="url" inputmode="url" autocapitalize="off" autocorrect="off" spellcheck="false" ' +
        'placeholder="http://192.168.1.10:8765" value="' + Dom.escape(app.serverUrl) + '"></label>' +
        '<div id="gate-found" class="chips">' + this.chips() + "</div>" +
        '<button class="btn" data-action="find">' + Icons.search + " Найти сервер в сети</button>"
      : "";
    return '<div class="gate">' +
      '<div class="gate-logo">' + Icons.power + "</div>" +
      '<h1 class="title center">Pulse</h1>' +
      '<p class="muted center small">Удалённое управление компьютером</p>' +
      '<div class="card form">' + server +
      '<label class="field"><span>Ключ доступа</span>' +
      '<input id="gate-token" type="text" autocapitalize="off" autocorrect="off" spellcheck="false" ' +
      'placeholder="Например: k7m2x9qa" value="' + Dom.escape(app.token) + '"></label>' +
      '<div class="form-error" id="gate-error">' + Dom.escape(message || "") + "</div>" +
      '<button class="btn primary" data-action="connect">Подключиться</button></div>' +
      '<p class="hint center">Ключ доступа показан на ПК с сервером: значок Pulse в трее → «Открыть панель» → ' +
      "значок настроек в правом верхнем углу.</p></div>";
  }

  chips() {
    return this.found
      .map((item) => '<button class="chip" data-action="pick" data-url="http://' + Dom.escape(item.address) +
        ":" + Dom.escape(item.port || 8765) + '">' + Dom.escape(item.name || item.address) + " · " +
        Dom.escape(item.address) + "</button>")
      .join("");
  }

  render(message) {
    this.app.root.innerHTML = this.template(message);
  }

  showError(text) {
    const element = Dom.byId("gate-error");
    if (element) {
      element.textContent = text;
    }
  }

  handle(event) {
    const target = event.target.closest("[data-action]");
    if (!target) {
      return;
    }
    const action = target.dataset.action;
    if (action === "pick") {
      Dom.byId("gate-url").value = target.dataset.url;
    } else if (action === "find") {
      this.find(target);
    } else if (action === "connect") {
      this.connect(target);
    }
  }

  async find(button) {
    button.disabled = true;
    this.showError("");
    try {
      const result = await Native.call("discover", 1800);
      this.found = result.servers || [];
      Dom.byId("gate-found").innerHTML = this.chips();
      if (!this.found.length) {
        this.showError("Серверы не найдены. Введите адрес вручную.");
      } else if (this.found.length === 1) {
        const only = this.found[0];
        Dom.byId("gate-url").value = "http://" + only.address + ":" + (only.port || 8765);
      }
    } catch (error) {
      this.showError(error.message);
    }
    button.disabled = false;
  }

  async connect(button) {
    const urlField = Dom.byId("gate-url");
    const url = urlField ? urlField.value : "";
    const token = Dom.byId("gate-token").value;
    button.disabled = true;
    this.showError("");
    try {
      await this.app.connect(url, token);
    } catch (error) {
      this.showError(error.message);
      button.disabled = false;
    }
  }
}

class HomeView {
  constructor(app) {
    this.app = app;
    this.last = "";
  }

  headerTemplate() {
    const app = this.app;
    const name = app.server ? app.server.name : "";
    const status = app.online
      ? '<i class="dot ok"></i>Подключено' + (name ? " · " + Dom.escape(name) : "")
      : '<i class="dot err"></i>Нет связи с сервером';
    return '<header class="header"><div><h1 class="title">Pulse</h1>' +
      '<button class="status" data-action="refresh">' + status + "</button></div>" +
      '<button class="icon-btn" data-action="settings" aria-label="Настройки">' + Icons.sliders + "</button></header>";
  }

  heroTemplate() {
    const app = this.app;
    const device = app.selected();
    const pending = app.pending[device.id];
    let state = "Статус неизвестен";
    let stateClass = "";
    if (!app.online) {
      state = "Нет связи с сервером";
    } else if (device.is_self) {
      state = "Этот компьютер · сервер работает на нём";
      stateClass = "ok";
    } else if (device.online === true) {
      state = "В сети";
      stateClass = "ok";
    } else if (device.online === false) {
      state = "Выключен";
    }
    if (pending === "wake") {
      state = "Отправляем Magic Packet…";
    } else if (pending === "shutdown") {
      state = "Выключаем…";
    }
    const powerClass = "power" + (pending ? " busy" : device.online === true && app.online ? " on" : "");
    const wakeDisabled = pending || device.is_self || (app.online && device.online === true);
    const shutdownDisabled = pending || !app.online || !device.can_shutdown;
    const hint = app.online && device.online === true && !device.is_self && !device.can_shutdown
      ? '<p class="hero-hint">Чтобы выключать этот ПК, установите на нём Pulse и включите «Есть сервер Pulse» в настройках устройства.</p>'
      : "";
    return '<section class="card hero">' +
      '<button class="' + powerClass + '" data-action="power"' + (pending ? " disabled" : "") +
      ' aria-label="Питание">' + Icons.power + "</button>" +
      '<div class="hero-name">' + Dom.escape(device.name) + "</div>" +
      '<div class="hero-state ' + stateClass + '">' + Dom.escape(state) + "</div>" +
      '<div class="hero-actions">' +
      '<button class="btn" data-action="wake"' + (wakeDisabled ? " disabled" : "") + ">Включить</button>" +
      '<button class="btn danger" data-action="shutdown"' + (shutdownDisabled ? " disabled" : "") + ">Выключить</button>" +
      "</div>" + hint + "</section>";
  }

  listTemplate() {
    const app = this.app;
    const rows = app.devices.map((device) =>
      '<div class="row' + (device.id === app.selectedId ? " selected" : "") + '" data-action="select" data-id="' + Dom.escape(device.id) + '">' +
      '<i class="dot ' + Format.dot(app, device) + '"></i>' +
      '<span class="row-main"><span class="row-title">' + Dom.escape(device.name) + Format.badges(device) + "</span>" +
      '<span class="row-sub mono">' + Format.sub(device) + "</span></span>" +
      '<button class="icon-btn small" data-action="edit" data-id="' + Dom.escape(device.id) + '" aria-label="Изменить">' + Icons.more + "</button></div>"
    ).join("");
    return '<div class="section-title">Мои компьютеры</div><section class="card list">' + rows + "</section>" +
      '<div class="footer-actions">' +
      '<button class="btn" data-action="discover">' + Icons.search + " Найти в сети</button>" +
      '<button class="btn" data-action="add">' + Icons.plus + " Вручную</button></div>";
  }

  emptyTemplate() {
    return '<section class="empty"><div class="empty-ring">' + Icons.monitor + "</div>" +
      "<h2>Устройств пока нет</h2>" +
      "<p>Найдём компьютеры в вашей сети Wi-Fi. Они должны быть включены и подключены к той же сети, что и телефон.</p>" +
      '<button class="btn primary" data-action="discover">' + Icons.search + " Найти компьютеры</button>" +
      '<button class="btn ghost" data-action="add">Добавить вручную</button></section>';
  }

  offlineTemplate() {
    return '<section class="empty"><div class="empty-ring">' + Icons.monitor + "</div>" +
      "<h2>Нет связи с сервером</h2>" +
      "<p>Проверьте, что телефон и ПК с Pulse подключены к одной сети Wi-Fi и сервер запущен.</p>" +
      '<button class="btn primary" data-action="refresh">Повторить</button>' +
      '<button class="btn ghost" data-action="settings">Настройки</button></section>';
  }

  template() {
    const app = this.app;
    let body;
    if (app.devices.length) {
      body = this.heroTemplate() + this.listTemplate();
    } else {
      body = app.online ? this.emptyTemplate() : this.offlineTemplate();
    }
    return this.headerTemplate() + body;
  }

  render(force) {
    const html = this.template();
    if (html !== this.last || force) {
      this.last = html;
      this.app.root.innerHTML = html;
    }
  }

  handle(event) {
    const target = event.target.closest("[data-action]");
    if (!target) {
      return;
    }
    const app = this.app;
    const id = target.dataset.id;
    const actions = {
      refresh: () => app.refresh(true),
      settings: () => app.openSettings(),
      power: () => app.onPower(),
      wake: () => app.wakeSelected(),
      shutdown: () => app.shutdownSelected(),
      select: () => app.select(id),
      edit: () => app.openDevice(id),
      discover: () => app.openDiscovery(),
      add: () => app.openDevice(null)
    };
    const run = actions[target.dataset.action];
    if (run) {
      run();
    }
  }
}

class DiscoverySheet {
  constructor(app) {
    this.app = app;
    this.sheet = new Sheet();
    this.found = [];
    this.error = "";
    this.scanning = false;
    this.showAll = false;
  }

  open() {
    this.sheet.open("Компьютеры в сети", this.template());
    this.sheet.clickHandler = (event) => this.handle(event);
    this.scan();
  }

  visible() {
    return this.found.filter((item) => item.name || this.showAll || item.agent);
  }

  template() {
    const visible = this.visible();
    const hidden = this.found.length - visible.length;
    const sorted = visible.slice().sort((a, b) => (b.agent - a.agent) || ((b.name ? 1 : 0) - (a.name ? 1 : 0)));
    const rows = sorted.map((item) => {
      const index = this.found.indexOf(item);
      const button = item.added
        ? '<button class="btn small ghost" disabled>Добавлено</button>'
        : '<button class="btn small" data-action="add-found" data-index="' + index + '">Добавить</button>';
      return '<div class="row static"><i class="dot ' + (item.agent ? "ok" : "unk") + '"></i>' +
        '<span class="row-main"><span class="row-title">' + Dom.escape(item.name || "Без названия") +
        (item.is_self ? '<em class="badge">Этот ПК</em>' : "") +
        (item.agent ? '<em class="badge ok">Pulse</em>' : "") + "</span>" +
        '<span class="row-sub mono">' + Dom.escape(item.host + " · " + item.mac) + "</span></span>" + button + "</div>";
    }).join("");
    const status = this.scanning ? "Идёт поиск…" : this.error ? this.error : "Найдено: " + visible.length;
    return '<p class="muted small">Компьютеры должны быть включены и подключены к той же сети Wi-Fi. ' +
      "Компьютеры с Pulse отмечены зелёным значком.</p>" +
      '<div class="progress' + (this.scanning ? " on" : "") + '"><i></i></div>' +
      '<div class="status-line' + (this.error && !this.scanning ? " err" : "") + '">' + Dom.escape(status) + "</div>" +
      (rows ? '<section class="card list">' + rows + "</section>" : "") +
      '<div class="sheet-actions"><label class="check"><input type="checkbox" data-action="toggle-all"' +
      (this.showAll ? " checked" : "") + "> Без названия (" + (this.showAll ? 0 : hidden) + ")</label>" +
      '<button class="btn" data-action="rescan"' + (this.scanning ? " disabled" : "") + ">" + Icons.refresh + " Искать снова</button></div>";
  }

  update() {
    this.sheet.setBody(this.template());
  }

  async scan() {
    this.scanning = true;
    this.error = "";
    this.update();
    try {
      const result = await this.app.api.scan();
      this.found = result.devices || [];
    } catch (error) {
      this.found = [];
      this.error = error.message;
    }
    this.scanning = false;
    if (this.sheet.isOpen) {
      this.update();
    }
  }

  handle(event) {
    const target = event.target.closest("[data-action]");
    if (!target) {
      return;
    }
    const action = target.dataset.action;
    if (action === "rescan") {
      this.scan();
    } else if (action === "toggle-all") {
      this.showAll = target.checked;
      this.update();
    } else if (action === "add-found") {
      this.addFound(Number(target.dataset.index));
    }
  }

  async addFound(index) {
    const item = this.found[index];
    if (!item) {
      return;
    }
    try {
      const device = await this.app.api.addDevice({
        name: item.name || item.host,
        mac: item.mac,
        host: item.host,
        port: item.port,
        agent: item.agent
      });
      item.added = true;
      await this.app.afterDeviceChanged(device);
      this.app.toast.show("Добавлено: " + device.name);
      this.update();
    } catch (error) {
      this.app.toast.error(error.message);
    }
  }
}

class DeviceSheet {
  constructor(app, device) {
    this.app = app;
    this.device = device;
    this.sheet = new Sheet();
  }

  open() {
    this.sheet.open(this.device ? "Устройство" : "Новое устройство", this.template());
    this.sheet.clickHandler = (event) => this.handle(event);
    this.sheet.changeHandler = (event) => this.change(event);
  }

  field(id, label, value, attributes) {
    return '<label class="field"><span>' + label + '</span><input id="' + id + '" type="text" ' +
      'autocapitalize="off" autocorrect="off" spellcheck="false" ' + (attributes || "") +
      ' value="' + Dom.escape(value) + '"></label>';
  }

  shortcutsTemplate() {
    const app = this.app;
    const wake = app.shortcutUrl("wake", this.device.id);
    const off = app.shortcutUrl("shutdown", this.device.id);
    const line = (text) => '<div class="copyline"><code>' + Dom.escape(text) + "</code>" +
      '<button class="icon-btn small" data-action="copy" data-text="' + Dom.escape(text) +
      '" aria-label="Копировать">' + Icons.copy + "</button></div>";
    return '<section class="card inset"><div class="label">Для приложения «Команды» на iPhone</div>' +
      '<p class="muted small">Действие «Получить содержимое URL» → вставьте ссылку. Включение работает, пока включён хотя бы один компьютер с Pulse.</p>' +
      '<div class="label">Включить</div>' + line(wake) +
      '<div class="label">Выключить</div>' + line(off) + "</section>";
  }

  template() {
    const d = this.device || {};
    const agent = d.agent === true;
    return '<div class="stack">' +
      this.field("dev-name", "Название", d.name || "", 'placeholder="Игровой ПК" maxlength="60"') +
      this.field("dev-mac", "MAC-адрес", d.mac || "", 'placeholder="AA:BB:CC:DD:EE:FF"') +
      this.field("dev-host", "IP-адрес или имя в сети", d.host || "", 'placeholder="192.168.1.50"') +
      '<div class="field-row">' +
      this.field("dev-broadcast", "Broadcast-адрес", d.broadcast || "255.255.255.255", 'inputmode="decimal"') +
      this.field("dev-wolport", "Порт Magic Packet", d.wol_port || 9, 'inputmode="numeric"') + "</div>" +
      '<label class="switch-row"><span>Есть сервер Pulse на этом ПК</span><span class="switch">' +
      '<input id="dev-agent" type="checkbox" data-action="toggle-agent"' + (agent ? " checked" : "") + "><i></i></span></label>" +
      '<div id="dev-port-field"' + (agent ? "" : " hidden") + ">" +
      this.field("dev-port", "Порт Pulse на этом ПК", d.port || 8765, 'inputmode="numeric"') + "</div>" +
      '<div class="form-error" id="dev-error"></div>' +
      '<button class="btn primary block" data-action="save">Сохранить</button>' +
      (this.device ? '<button class="btn danger block" data-action="delete">' + Icons.trash + " Удалить устройство</button>" : "") +
      "</div>" + (this.device ? this.shortcutsTemplate() : "");
  }

  change(event) {
    if (event.target && event.target.id === "dev-agent") {
      Dom.byId("dev-port-field").hidden = !event.target.checked;
    }
  }

  handle(event) {
    const target = event.target.closest("[data-action]");
    if (!target) {
      return;
    }
    const action = target.dataset.action;
    if (action === "save") {
      this.save(target);
    } else if (action === "delete") {
      this.remove();
    } else if (action === "copy") {
      Clipboard.copy(target.dataset.text).then((ok) => {
        if (ok) {
          this.app.toast.show("Ссылка скопирована");
        } else {
          this.app.toast.error("Не удалось скопировать — выделите ссылку вручную");
        }
      });
    }
  }

  value(id) {
    return Dom.byId(id).value.trim();
  }

  async save(button) {
    const data = {
      name: this.value("dev-name"),
      mac: this.value("dev-mac"),
      host: this.value("dev-host"),
      broadcast: this.value("dev-broadcast") || "255.255.255.255",
      wol_port: parseInt(this.value("dev-wolport"), 10) || 9,
      agent: Dom.byId("dev-agent").checked,
      port: parseInt(this.value("dev-port"), 10) || 8765
    };
    const error = Dom.byId("dev-error");
    if (!data.name || !data.mac) {
      error.textContent = "Укажите название и MAC-адрес";
      return;
    }
    button.disabled = true;
    try {
      const saved = this.device
        ? await this.app.api.updateDevice(this.device.id, data)
        : await this.app.api.addDevice(data);
      this.sheet.close();
      await this.app.afterDeviceChanged(saved);
    } catch (problem) {
      error.textContent = problem.message;
      button.disabled = false;
    }
  }

  async remove() {
    const ok = await Dialog.confirm({
      title: "Удалить «" + this.device.name + "»?",
      text: "Устройство исчезнет из списка. Сам компьютер не изменится.",
      confirm: "Удалить",
      danger: true
    });
    if (!ok) {
      return;
    }
    try {
      await this.app.api.removeDevice(this.device.id);
      this.sheet.close();
      await this.app.afterDeviceChanged(null);
    } catch (error) {
      this.app.toast.error(error.message);
    }
  }
}

class SettingsSheet {
  constructor(app) {
    this.app = app;
    this.sheet = new Sheet();
  }

  open() {
    this.sheet.open("Настройки", this.template());
    this.sheet.clickHandler = (event) => this.handle(event);
  }

  template() {
    const app = this.app;
    const server = app.server;
    let body = "";
    if (server) {
      const urls = (server.urls || []).map((url) => Dom.escape(url)).join("<br>") || "—";
      body += '<section class="card inset"><div class="kv"><span>Сервер</span><b>' + Dom.escape(server.name) + "</b></div>" +
        '<div class="kv"><span>Версия</span><b>' + Dom.escape(server.version) + "</b></div>" +
        '<div class="kv"><span>Адреса</span><b class="mono">' + urls + "</b></div></section>";
      if (server.autostart !== null && server.autostart !== undefined) {
        body += '<label class="switch-row"><span>Запускать вместе с Windows</span><span class="switch">' +
          '<input type="checkbox" data-action="autostart"' + (server.autostart ? " checked" : "") + "><i></i></span></label>";
      }
      const link = app.phoneLink();
      body += '<section class="card inset"><div class="label">Ссылка для телефона (с ключом доступа)</div>' +
        '<div class="copyline"><code>' + Dom.escape(link) + '</code><button class="icon-btn small" data-action="copy" data-text="' +
        Dom.escape(link) + '" aria-label="Копировать">' + Icons.copy + "</button></div>" +
        '<p class="muted small">Откройте ссылку в Safari и выберите «Поделиться → На экран “Домой”». ' +
        "Не публикуйте её: по ней можно выключать компьютеры.</p></section>";
    } else {
      body += '<p class="muted small">Нет данных о сервере: нет связи.</p>';
    }
    if (app.native) {
      body += '<button class="btn block" data-action="change-server">Сменить сервер</button>';
    }
    body += '<button class="btn danger block" data-action="logout">Выйти</button>';
    return body;
  }

  handle(event) {
    const target = event.target.closest("[data-action]");
    if (!target) {
      return;
    }
    const action = target.dataset.action;
    if (action === "copy") {
      Clipboard.copy(target.dataset.text).then((ok) => {
        if (ok) {
          this.app.toast.show("Ссылка скопирована");
        } else {
          this.app.toast.error("Не удалось скопировать");
        }
      });
    } else if (action === "autostart") {
      this.toggleAutostart(target);
    } else if (action === "logout" || action === "change-server") {
      this.sheet.close();
      this.app.logout("");
    }
  }

  async toggleAutostart(checkbox) {
    const wanted = checkbox.checked;
    try {
      const result = await this.app.api.setAutostart(wanted);
      this.app.server.autostart = result.autostart;
      this.app.toast.show(result.autostart ? "Автозапуск включён" : "Автозапуск выключен");
    } catch (error) {
      checkbox.checked = !wanted;
      this.app.toast.error(error.message);
    }
  }
}
