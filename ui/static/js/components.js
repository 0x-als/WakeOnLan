class Dom {
  static escape(value) {
    const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, (char) => map[char]);
  }

  static byId(id) {
    return document.getElementById(id);
  }
}

class Clipboard {
  static async copy(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (error) {
      /* fall back to the legacy path below */
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    area.setSelectionRange(0, text.length);
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (error) {
      ok = false;
    }
    document.body.removeChild(area);
    return ok;
  }
}

class Toast {
  constructor(root) {
    this.root = root;
    this.timer = null;
  }

  show(message, options) {
    const settings = options || {};
    this.root.innerHTML = "";
    const element = document.createElement("div");
    element.className = "toast" + (settings.error ? " error" : "");
    element.innerHTML = "<span>" + Dom.escape(message) + "</span>" +
      (settings.action ? "<button>" + Dom.escape(settings.action) + "</button>" : "");
    if (settings.action) {
      element.querySelector("button").addEventListener("click", () => {
        this.hide();
        if (settings.onAction) {
          settings.onAction();
        }
      });
    }
    this.root.appendChild(element);
    requestAnimationFrame(() => element.classList.add("show"));
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.hide(), settings.duration || 3500);
  }

  error(message) {
    this.show(message, { error: true, duration: 5000 });
  }

  hide() {
    const element = this.root.firstChild;
    if (!element) {
      return;
    }
    element.classList.remove("show");
    setTimeout(() => {
      if (element.parentNode) {
        element.parentNode.removeChild(element);
      }
    }, 220);
  }
}

class Sheet {
  constructor() {
    this.backdrop = null;
    this.body = null;
    this.clickHandler = null;
    this.changeHandler = null;
  }

  get isOpen() {
    return this.backdrop !== null;
  }

  open(title, html) {
    this.close();
    const backdrop = document.createElement("div");
    backdrop.className = "backdrop";
    backdrop.innerHTML =
      '<div class="sheet" role="dialog"><div class="grabber"></div>' +
      '<div class="sheet-head"><h2>' + Dom.escape(title) + "</h2>" +
      '<button class="icon-btn small" data-sheet-close aria-label="Закрыть">' + Icons.close + "</button></div>" +
      '<div class="sheet-body">' + html + "</div></div>";
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop || event.target.closest("[data-sheet-close]")) {
        this.close();
        return;
      }
      if (this.clickHandler) {
        this.clickHandler(event);
      }
    });
    backdrop.addEventListener("change", (event) => {
      if (this.changeHandler) {
        this.changeHandler(event);
      }
    });
    document.body.appendChild(backdrop);
    document.body.classList.add("locked");
    requestAnimationFrame(() => backdrop.classList.add("show"));
    this.backdrop = backdrop;
    this.body = backdrop.querySelector(".sheet-body");
    Sheet.current = this;
  }

  setBody(html) {
    if (this.body) {
      this.body.innerHTML = html;
    }
  }

  close() {
    if (!this.backdrop) {
      return;
    }
    const backdrop = this.backdrop;
    this.backdrop = null;
    this.body = null;
    if (Sheet.current === this) {
      Sheet.current = null;
    }
    document.body.classList.remove("locked");
    backdrop.classList.remove("show");
    setTimeout(() => {
      if (backdrop.parentNode) {
        backdrop.parentNode.removeChild(backdrop);
      }
    }, 280);
  }
}

Sheet.current = null;

class Dialog {
  static confirm(options) {
    return new Promise((resolve) => {
      const backdrop = document.createElement("div");
      backdrop.className = "backdrop center";
      backdrop.innerHTML =
        '<div class="dialog" role="alertdialog"><h3>' + Dom.escape(options.title) + "</h3>" +
        "<p>" + Dom.escape(options.text || "") + "</p>" +
        '<div class="dialog-actions"><button class="btn" data-result="no">Отмена</button>' +
        '<button class="btn ' + (options.danger ? "danger" : "primary") + '" data-result="yes">' +
        Dom.escape(options.confirm || "Да") + "</button></div></div>";
      const finish = (value) => {
        Dialog.current = null;
        backdrop.classList.remove("show");
        setTimeout(() => {
          if (backdrop.parentNode) {
            backdrop.parentNode.removeChild(backdrop);
          }
        }, 220);
        resolve(value);
      };
      backdrop.addEventListener("click", (event) => {
        const button = event.target.closest("[data-result]");
        if (button) {
          finish(button.dataset.result === "yes");
        } else if (event.target === backdrop) {
          finish(false);
        }
      });
      document.body.appendChild(backdrop);
      requestAnimationFrame(() => backdrop.classList.add("show"));
      Dialog.current = () => finish(false);
    });
  }
}

Dialog.current = null;
