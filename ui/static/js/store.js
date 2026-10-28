class Store {
  static get(key, fallback) {
    try {
      const raw = window.localStorage.getItem("pulse." + key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch (error) {
      return fallback;
    }
  }

  static set(key, value) {
    try {
      window.localStorage.setItem("pulse." + key, JSON.stringify(value));
    } catch (error) {
      return;
    }
  }

  static remove(key) {
    try {
      window.localStorage.removeItem("pulse." + key);
    } catch (error) {
      return;
    }
  }
}
