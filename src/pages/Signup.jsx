import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";

export default function Signup() {
  const nav = useNavigate();

  const [first_name, setFirst] = useState("");
  const [last_name, setLast] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // ✅ يقرأ JSON لو موجود، ولو الرد نص/فاضي يرجع object فيه error/detail
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
      // 1) Register فقط
      const r1 = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ first_name, last_name, phone, email, password }),
      });

      const d1 = await safeJson(r1);

      if (!r1.ok) {
        throw new Error(d1?.detail || d1?.error || "Signup failed");
      }

      // ✅ لا نسوي login هنا
      // ✅ اختياري: نظف الفورم
      setFirst("");
      setLast("");
      setPhone("");
      setEmail("");
      setPassword("");

      // ✅ تحويل لصفحة تسجيل الدخول
      nav("/login");
    } catch (err) {
      setError(err?.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-sm border p-6">
        <h1 className="text-2xl font-semibold">Sign up</h1>
        <p className="text-slate-500 mt-1">Create your Hemaya account</p>

        {error && (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-slate-600">First name</label>
              <input
                className="mt-1 w-full rounded-xl border px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-200"
                value={first_name}
                onChange={(e) => setFirst(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-sm text-slate-600">Last name</label>
              <input
                className="mt-1 w-full rounded-xl border px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-200"
                value={last_name}
                onChange={(e) => setLast(e.target.value)}
                required
              />
            </div>
          </div>

          <div>
            <label className="text-sm text-slate-600">Phone</label>
            <input
              className="mt-1 w-full rounded-xl border px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-200"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="05xxxxxxxx"
              required
            />
          </div>

          <div>
            <label className="text-sm text-slate-600">Email</label>
            <input
              className="mt-1 w-full rounded-xl border px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-200"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
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
              minLength={6}
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-emerald-600 text-white py-2.5 font-medium hover:bg-emerald-700 disabled:opacity-60"
          >
            {loading ? "Creating..." : "Create account"}
          </button>
        </form>

        <div className="mt-5 text-sm text-slate-600">
          Already have an account?{" "}
          <Link className="text-emerald-700 font-medium hover:underline" to="/login">
            Login
          </Link>
        </div>
      </div>
    </div>
  );
}
