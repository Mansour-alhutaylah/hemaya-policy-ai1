import { clearAssistantSessions } from "@/lib/utils";

// In production, VITE_API_URL = "https://hemaya-policy-ai1.onrender.com/api"
// In local dev, fall back to "/api" (Vite proxy handles it).
const API_BASE = import.meta.env.VITE_API_URL || "/api";

async function request(method, url, data, opts = {}) {
  const token = localStorage.getItem("token");
  const headers = {};

  if (!(data instanceof FormData)) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const options = { method, headers };
  if (data) options.body = data instanceof FormData ? data : JSON.stringify(data);
  if (opts.signal) options.signal = opts.signal;

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
      clearAssistantSessions();
      window.location.href = "/login";
      // Throw so any awaiting caller also stops execution
      throw new Error("Session expired. Please log in again.");
    }

    const text = await res.text();
    if (isJson && text) {
      try {
        const j = JSON.parse(text);
        const detail = j.detail;
        let msg;
        if (Array.isArray(detail)) {
          // FastAPI validation error list
          msg = detail.map((e) => e.msg || e.message || JSON.stringify(e)).join(", ");
        } else if (detail && typeof detail === "object") {
          // Structured error object (e.g. frameworks_not_ready 409)
          msg = detail.message || detail.error || JSON.stringify(detail);
        } else {
          msg = detail || j.error || "Request failed";
        }
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
    changePassword: (data) => request("POST", "/auth/change-password", data),
    logout: (redirectUrl) => {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      clearAssistantSessions();
      window.location.href = redirectUrl || "/";
    },
  },
  entities: new Proxy({}, entityHandler),
  functions: {
    invoke: (name, args, opts) => request("POST", `/functions/${name}`, args, opts),
  },
  assistant: {
    // Phase F: optional policy_id scopes the chatbot to a single policy.
    // When omitted, the assistant falls back to the user's full portfolio.
    chat: (message, { policy_id, ...opts } = {}) =>
      request(
        "POST",
        "/assistant/chat",
        policy_id ? { message, policy_id } : { message },
        opts,
      ),
  },
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
