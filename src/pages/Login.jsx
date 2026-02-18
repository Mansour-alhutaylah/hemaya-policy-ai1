import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../lib/AuthContext";

export default function Login() {
  const nav = useNavigate();
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // ✅ يحاول يقرأ JSON لو موجود، ولو الرد نص/فاضي يرجّع object مناسب
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
    setLoading(true);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await safeJson(res);

      if (!res.ok) {
        throw new Error(
          data?.detail || data?.error || data?.message || "Login failed"
        );
      }

      // ✅ بعض السيرفرات ترجع access_token بدل token
      const token = data?.token || data?.access_token;
      if (!token) throw new Error("Login response missing token/access_token");

      // ✅ user ممكن يرجع داخل data.user
      let user = data?.user || null;

      // ✅ إذا ما رجّع user، نجيبها من /auth/me بعد ما نخزن التوكن
      if (!user) {
        localStorage.setItem("token", token);
        const meRes = await fetch("/api/auth/me", {
          headers: { Authorization: `Bearer ${token}` },
        });
        const meData = await safeJson(meRes);
        if (meRes.ok) user = meData;
      }

      login({ token, user });
      nav("/dashboard");
    } catch (err) {
      setError(err?.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-sm border p-6">
        <h1 className="text-2xl font-semibold">Login</h1>
        <p className="text-slate-500 mt-1">Sign in to Hemaya</p>

        {error && (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div>
            <label className="text-sm text-slate-600">Email</label>
            <input
              className="mt-1 w-full rounded-xl border px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-200"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              placeholder="you@company.com"
              required
            />
          </div>

          <div>
            <label className="text-sm text-slate-600">Password</label>
            <input
              className="mt-1 w-full rounded-xl border px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-200"
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
            className="w-full rounded-xl bg-emerald-600 text-white py-2.5 font-medium hover:bg-emerald-700 disabled:opacity-60"
          >
            {loading ? "Signing in..." : "Login"}
          </button>
        </form>

        <div className="mt-5 text-sm text-slate-600">
          Don&apos;t have an account?{" "}
          <Link className="text-emerald-700 font-medium hover:underline" to="/signup">
            Sign up
          </Link>
        </div>
      </div>
    </div>
  );
}
