import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "@/components/ui/input-otp";
import StatusAlert from "@/components/ui/StatusAlert";
import ThemeToggle from "@/components/ThemeToggle";
import { useAuth } from "@/lib/AuthContext";

const API = import.meta.env.VITE_API_URL || "/api";

export default function VerifyOTP() {
  const nav = useNavigate();
  const { login } = useAuth();
  const [searchParams] = useSearchParams();
  const email = searchParams.get("email") || "";
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  // Cooldown starts at 0 — the OTP was already sent during login/signup,
  // so the user should be able to enter it immediately. The timer only
  // starts after the user explicitly clicks "Resend code".
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function handleVerify(e) {
    e.preventDefault();
    if (otp.length !== 6) return;
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/verify-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Verification failed");

      // Backend returns a JWT + user object — auto-login without a second
      // password prompt.
      const token = data?.access_token || data?.token;
      const userData = data?.user || null;

      if (token) {
        // Call login() then navigate in the same tick so React batches both
        // the AuthContext state update and the route change into a single
        // render. This prevents the 800ms window where the authenticated
        // Routes block renders at /verify-otp and shows <PageNotFound>.
        login({ token, user: userData });
        nav(userData?.is_admin ? "/admin" : "/Dashboard", { replace: true });
      } else {
        // Fallback: backend didn't issue a token (e.g. older deploy).
        setSuccess("Email verified! Redirecting to login…");
        setTimeout(() => nav("/login", { replace: true }), 1000);
      }
    } catch (err) {
      setError(err.message || "Verification failed");
      setOtp("");
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    if (cooldown > 0 || loading) return;
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/resend-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Could not resend code");
      setCooldown(60);
      setOtp("");
    } catch (err) {
      setError(err.message || "Could not resend code");
    } finally {
      setLoading(false);
    }
  }

  return (
    // Phase UI-9: shared auth-page ambient gradient.
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

          <h1 className="text-2xl font-semibold tracking-tight">Verify your email</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Enter the 6-digit code sent to{" "}
            <span className="font-medium text-foreground">{email}</span>
          </p>

          <StatusAlert type="error" message={error} className="mt-4" />
          <StatusAlert type="success" message={success} className="mt-4" />

          <form onSubmit={handleVerify} className="mt-6 space-y-5">
            <div className="flex justify-center">
              <InputOTP maxLength={6} value={otp} onChange={setOtp}>
                <InputOTPGroup>
                  {[0, 1, 2, 3, 4, 5].map((i) => (
                    <InputOTPSlot key={i} index={i} className="h-12 w-12 text-lg" />
                  ))}
                </InputOTPGroup>
              </InputOTP>
            </div>

            <button
              type="submit"
              disabled={loading || otp.length !== 6}
              className="w-full rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white py-2.5 font-medium shadow-sm shadow-emerald-500/20 disabled:opacity-60 transition-colors"
            >
              {loading ? "Verifying…" : "Verify email"}
            </button>
          </form>

          <div className="mt-5 text-sm text-muted-foreground text-center">
            Didn&apos;t receive the code?{" "}
            {cooldown > 0 ? (
              <span className="text-muted-foreground/70">Resend in {cooldown}s</span>
            ) : (
              <button
                onClick={handleResend}
                disabled={loading}
                className="font-medium text-emerald-600 dark:text-emerald-400 hover:underline disabled:opacity-60"
              >
                Resend code
              </button>
            )}
          </div>

          <div className="mt-3 text-sm text-center">
            <Link
              className="text-muted-foreground hover:text-foreground hover:underline"
              to="/login"
            >
              Back to login
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
