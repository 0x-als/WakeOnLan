class Native {
  static get available() {
    return typeof window.PulseNative !== "undefined";
  }

  static call(method, ...args) {
    return new Promise((resolve, reject) => {
      if (!Native.available) {
        reject(new Error("Недоступно в браузере"));
        return;
      }
      const id = "cb" + ++Native.counter;
      const timer = setTimeout(() => {
        delete Native.pending[id];
        reject(new Error("Приложение не ответило"));
      }, 12000);
      Native.pending[id] = { resolve, reject, timer };
      try {
        window.PulseNative[method](id, ...args);
      } catch (error) {
        clearTimeout(timer);
        delete Native.pending[id];
        reject(error);
      }
    });
  }

  static resolve(id, payload) {
    const entry = Native.pending[id];
    if (!entry) {
      return;
    }
    clearTimeout(entry.timer);
    delete Native.pending[id];
    if (payload && payload.error) {
      entry.reject(new Error(payload.error));
    } else {
      entry.resolve(payload);
    }
  }
}

Native.counter = 0;
Native.pending = {};
window.PulseNativeResolve = (id, payload) => Native.resolve(id, payload);
