import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import StatusAlert from "@/components/ui/StatusAlert";
import PasswordStrengthChecker from "@/components/ui/PasswordStrengthChecker";
import ThemeToggle from "@/components/ThemeToggle";

const API = import.meta.env.VITE_API_URL || "/api";

export default function Signup() {
  const nav = useNavigate();

  const [first_name, setFirst] = useState("");
  const [last_name, setLast] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
    setLoading(true);

    try {
      const r1 = await fetch(`${API}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ first_name, last_name, phone, email, password }),
      });

      const d1 = await safeJson(r1);

      if (!r1.ok) {
        const detail = d1?.detail;
        const msg = Array.isArray(detail)
          ? detail.map((e) => e.msg || e.message || JSON.stringify(e)).join(", ")
          : detail || d1?.error || "Signup failed";
        throw new Error(msg);
      }

      nav(`/verify-otp?email=${encodeURIComponent(email)}`);
    } catch (err) {
      setError(err?.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  const inputClass =
    "mt-1 w-full rounded-xl border border-input bg-background text-foreground placeholder:text-muted-foreground/70 px-3 py-2 outline-none focus:ring-2 focus:ring-ring focus:border-ring transition-colors";

  return (
    // Phase UI-9: matches Login's ambient gradient — same emerald glow on
    // both auth pages so the auth flow feels visually continuous.
    <div className="relative min-h-screen flex items-center justify-center bg-background text-foreground px-4 py-10 overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-60 dark:opacity-40"
        style={{
          background:
            'radial-gradient(60% 40% at 50% 0%, rgba(16,185,129,0.15), transparent 65%),' +
            'radial-gradient(45% 35% at 90% 100%, rgba(20,184,166,0.10), transparent 70%)',
        }}
      />
      <ThemeToggle />

      <div className="w-full max-w-md relative">
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

          <h1 className="text-2xl font-semibold tracking-tight">Sign up</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Create your Himaya account
          </p>

          <StatusAlert type="error" message={error} className="mt-4" />

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm text-muted-foreground">First name</label>
                <input
                  className={inputClass}
                  value={first_name}
                  onChange={(e) => setFirst(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="text-sm text-muted-foreground">Last name</label>
                <input
                  className={inputClass}
                  value={last_name}
                  onChange={(e) => setLast(e.target.value)}
                  required
                />
              </div>
            </div>

            <div>
              <label className="text-sm text-muted-foreground">Phone</label>
              <input
                className={inputClass}
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="05xxxxxxxx"
                required
              />
            </div>

            <div>
              <label className="text-sm text-muted-foreground">Email</label>
              <input
                className={inputClass}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                type="email"
                required
              />
            </div>

            <div>
              <label className="text-sm text-muted-foreground">Password</label>
              <input
                className={inputClass}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                minLength={8}
                required
              />
              <PasswordStrengthChecker password={password} />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white py-2.5 font-medium shadow-sm shadow-emerald-500/20 disabled:opacity-60 transition-colors"
            >
              {loading ? "Creating..." : "Create account"}
            </button>
          </form>

          <div className="mt-5 text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link
              className="font-medium text-emerald-600 dark:text-emerald-400 hover:underline"
              to="/login"
            >
              Login
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
