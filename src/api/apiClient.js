const API_BASE = "/api";

async function request(method, url, data) {
  const token = localStorage.getItem("token");
  const headers = {};

  if (!(data instanceof FormData)) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const options = { method, headers };
  if (data) options.body = data instanceof FormData ? data : JSON.stringify(data);

  const res = await fetch(`${API_BASE}${url}`, options);

  const contentType = res.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");

  if (!res.ok) {
    // 401 anywhere in the app means the token is expired or invalid — force logout
    if (res.status === 401) {
      try {
        sessionStorage.setItem("logout_reason", "expired");
      } catch { /* storage unavailable */ }
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      localStorage.removeItem("session_timeout_minutes");
      window.location.href = "/login";
      // Throw so any awaiting caller also stops execution
      throw new Error("Session expired. Please log in again.");
    }

    const text = await res.text();
    if (isJson && text) {
      try {
        const j = JSON.parse(text);
        const detail = j.detail;
        const msg = Array.isArray(detail)
          ? detail.map((e) => e.msg || e.message || JSON.stringify(e)).join(", ")
          : detail || j.error || "Request failed";
        throw new Error(msg);
      } catch (parseErr) {
        if (!(parseErr instanceof SyntaxError)) throw parseErr;
      }
    }
    throw new Error(text || "Request failed");
  }

  if (res.status === 204) return null;
  if (isJson) return res.json();

  return res.text();
}

const entityHandler = {
  get: (target, entityName) => ({
    get: (id) => request("GET", `/entities/${entityName}/${id}`),
    update: (id, data) => request("POST", `/entities/${entityName}`, { ...data, id }),
    filter: (query) => {
      const params = new URLSearchParams(query || {});
      return request("GET", `/entities/${entityName}?${params.toString()}`);
    },
    list: (sort, limit) =>
      request("GET", `/entities/${entityName}?sort=${sort || ""}&limit=${limit || 100}`),
    create: (data) => request("POST", `/entities/${entityName}`, data),
    delete: (id) => request("DELETE", `/entities/${entityName}/${id}`),
  }),
};

export const api = {
  auth: {
    me: () => request("GET", "/auth/me"),
    updateMe: (data) => request("POST", "/auth/updateMe", data),
    logout: (redirectUrl) => {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      window.location.href = redirectUrl || "/";
    },
  },
  entities: new Proxy({}, entityHandler),
  functions: { invoke: (name, args) => request("POST", `/functions/${name}`, args) },
  integrations: {
    Core: {
      UploadFile: async ({ file }) => {
        const form = new FormData();
        form.append("file", file);
        return request("POST", "/integrations/upload", form);
      },
    },
  },
};
