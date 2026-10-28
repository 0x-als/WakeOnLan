class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

class ApiClient {
  constructor(baseUrl, token) {
    this.baseUrl = (baseUrl || "").replace(/\/+$/, "");
    this.token = token || "";
  }

  static normalizeUrl(value) {
    let url = (value || "").trim();
    if (!url) {
      return "";
    }
    if (!/^https?:\/\//i.test(url)) {
      url = "http://" + url;
    }
    url = url.replace(/\/+$/, "");
    if (!/:\d+$/.test(url.replace(/^https?:\/\//i, "").split("/")[0])) {
      url += ":8765";
    }
    return url;
  }

  static messageFrom(data, status) {
    if (data && typeof data.detail === "string") {
      return data.detail;
    }
    if (data && Array.isArray(data.detail)) {
      return data.detail
        .map((item) => String(item.msg || "").replace(/^Value error, /, ""))
        .filter(Boolean)
        .join("; ");
    }
    return status === 401 ? "Неверный ключ доступа" : "Ошибка сервера (" + status + ")";
  }

  async request(method, path, body, timeout) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout || 12000);
    const headers = { "Content-Type": "application/json" };
    if (this.token) {
      headers["X-Pulse-Token"] = this.token;
    }
    try {
      const response = await fetch(this.baseUrl + path, {
        method: method,
        headers: headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal
      });
      const text = await response.text();
      let data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch (error) {
        data = null;
      }
      if (!response.ok) {
        throw new ApiError(ApiClient.messageFrom(data, response.status), response.status);
      }
      return data;
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      const message = error && error.name === "AbortError" ? "Сервер не отвечает" : "Нет связи с сервером";
      throw new ApiError(message, 0);
    } finally {
      clearTimeout(timer);
    }
  }

  health() { return this.request("GET", "/api/health", undefined, 4000); }
  info() { return this.request("GET", "/api/info", undefined, 6000); }
  devices() { return this.request("GET", "/api/devices", undefined, 15000); }
  addDevice(data) { return this.request("POST", "/api/devices", data); }
  updateDevice(id, data) { return this.request("PUT", "/api/devices/" + id, data); }
  removeDevice(id) { return this.request("DELETE", "/api/devices/" + id); }
  wake(id) { return this.request("POST", "/api/devices/" + id + "/wake"); }
  shutdown(id, delay, force) { return this.request("POST", "/api/devices/" + id + "/shutdown", { delay: delay, force: !!force }, 15000); }
  cancel(id) { return this.request("POST", "/api/devices/" + id + "/cancel", {}, 15000); }
  scan() { return this.request("POST", "/api/discovery/scan", undefined, 30000); }
  setAutostart(enabled) { return this.request("PUT", "/api/system/autostart", { enabled: !!enabled }); }
}
