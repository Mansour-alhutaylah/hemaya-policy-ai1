import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { useAuth } from "../lib/AuthContext";
import ThemeToggle from "@/components/ThemeToggle";
import StatusAlert from "@/components/ui/StatusAlert";

export default function Login() {
  const nav = useNavigate();
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(() => {
    try {
      const reason = sessionStorage.getItem("logout_reason");
      if (reason) {
        sessionStorage.removeItem("logout_reason");
        if (reason === "inactivity") return "You were signed out due to inactivity. Please log in again.";
        if (reason === "expired")    return "Session expired. Please log in again.";
      }
    } catch {
      // storage may be unavailable
    }
    return "";
  });

  // Try to parse a JSON body when present; otherwise fall back to text/empty.
  async function safeJson(res) {
    const contentType = res.headers.get("content-type") || "";
    const text = await res.text();
    if (!text) return null;

    if (contentType.includes("application/json")) {
      try {
        return JSON.parse(text);
      } catch {
        return { error: "Invalid JSON response", raw: text };
      }
    }

    return { error: text };
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setNotice("");
    setLoading(true);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12000);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      const data = await safeJson(res);

      if (!res.ok) {
        throw new Error(
          data?.detail || data?.error || data?.message || "Login failed"
        );
      }

      const token = data?.token || data?.access_token;
      if (!token) throw new Error("Login response missing token/access_token");

      let user = data?.user || null;

      if (!user) {
        localStorage.setItem("token", token);
        const meRes = await fetch("/api/auth/me", {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(8000),
        });
        const meData = await safeJson(meRes);
        if (meRes.ok) user = meData;
      }

      login({ token, user, session_timeout_minutes: data?.session_timeout_minutes });
      nav(user?.email === "himayaadmin@gmail.com" ? "/admin" : "/Dashboard");
    } catch (err) {
      clearTimeout(timeoutId);
      if (err?.name === "AbortError" || err?.name === "TimeoutError") {
        setError("Server is taking too long to respond. The database may be waking up — please try again in a moment.");
      } else {
        setError(err?.message || "Unknown error");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center bg-background text-foreground px-4 py-10">
      <ThemeToggle />

      <div className="w-full max-w-md">
        {/* Back to Home — sits above the card so it never collides with the form */}
        <div className="mb-4">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Home
          </Link>
        </div>

        <div className="rounded-2xl bg-card text-card-foreground border border-border shadow-sm p-6">
          {/* Logo / brand block — matches Landing's identity */}
          <div className="flex items-center gap-3 mb-5">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center shadow-sm shadow-emerald-500/20">
              <ShieldCheck className="w-5 h-5 text-white" />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold tracking-tight">Himaya</p>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
                AI Compliance
              </p>
            </div>
          </div>

          <h1 className="text-2xl font-semibold tracking-tight">Login</h1>
          <p className="text-muted-foreground mt-1 text-sm">Sign in to Himaya</p>

          {notice && !error && (
            <StatusAlert type="warning" message={notice} className="mt-4" />
          )}
          {error && (
            <StatusAlert type="error" message={error} className="mt-4" />
          )}

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div>
              <label htmlFor="login-email" className="text-sm text-muted-foreground">
                Email
              </label>
              <input
                id="login-email"
                className="mt-1 w-full rounded-xl border border-input bg-background text-foreground placeholder:text-muted-foreground/70 px-3 py-2 outline-none focus:ring-2 focus:ring-ring focus:border-ring transition-colors"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                type="email"
                placeholder="you@company.com"
                required
              />
            </div>

            <div>
              <label htmlFor="login-password" className="text-sm text-muted-foreground">
                Password
              </label>
              <input
                id="login-password"
                className="mt-1 w-full rounded-xl border border-input bg-background text-foreground placeholder:text-muted-foreground/70 px-3 py-2 outline-none focus:ring-2 focus:ring-ring focus:border-ring transition-colors"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                placeholder="••••••••"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white py-2.5 font-medium shadow-sm shadow-emerald-500/20 disabled:opacity-60 transition-colors"
            >
              {loading ? "Signing in..." : "Login"}
            </button>
          </form>

          <div className="mt-4 text-right">
            <Link
              className="text-sm text-muted-foreground hover:text-foreground hover:underline"
              to="/forgot-password"
            >
              Forgot password?
            </Link>
          </div>

          <div className="mt-3 text-sm text-muted-foreground">
            Don&apos;t have an account?{" "}
            <Link
              className="font-medium text-emerald-600 dark:text-emerald-400 hover:underline"
              to="/signup"
            >
              Sign up
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
