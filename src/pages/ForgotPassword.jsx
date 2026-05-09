import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "@/components/ui/input-otp";
import StatusAlert from "@/components/ui/StatusAlert";
import PasswordStrengthChecker from "@/components/ui/PasswordStrengthChecker";
import ThemeToggle from "@/components/ThemeToggle";

const API = import.meta.env.VITE_API_URL || "/api";

const inputClass =
  "mt-1 w-full rounded-xl border border-input bg-background text-foreground placeholder:text-muted-foreground/70 px-3 py-2 outline-none focus:ring-2 focus:ring-ring focus:border-ring transition-colors";

// Step 1 — enter email and request a reset code
function StepEmail({ onSuccess }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Request failed");
      onSuccess(email);
    } catch (err) {
      setError(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Forgot password</h1>
      <p className="text-muted-foreground mt-1 text-sm">
        Enter your email and we&apos;ll send you a reset code.
      </p>

      <StatusAlert type="error" message={error} className="mt-4" />

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <div>
          <label className="text-sm text-muted-foreground">Email</label>
          <input
            className={inputClass}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            required
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white py-2.5 font-medium shadow-sm shadow-emerald-500/20 disabled:opacity-60 transition-colors"
        >
          {loading ? "Sending…" : "Send reset code"}
        </button>
      </form>
    </>
  );
}

// Step 2 — enter the OTP received by email
function StepOTP({ email, onSuccess }) {
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [cooldown, setCooldown] = useState(60);

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
      const res = await fetch(`${API}/auth/verify-reset-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Verification failed");
      onSuccess(data.reset_token);
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
      const res = await fetch(`${API}/auth/forgot-password`, {
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
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Enter reset code</h1>

      <StatusAlert
        type="info"
        message={`If an account exists for ${email}, a 6-digit code has been sent. Check your inbox and spam folder.`}
        className="mt-3"
      />

      <StatusAlert type="error" message={error} className="mt-3" />

      <form onSubmit={handleVerify} className="mt-5 space-y-5">
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
          {loading ? "Verifying…" : "Verify code"}
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
    </>
  );
}

// Step 3 — set new password
function StepNewPassword({ resetToken }) {
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleReset(e) {
    e.preventDefault();
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reset_token: resetToken, new_password: password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Reset failed");
      nav("/login");
    } catch (err) {
      setError(err.message || "Reset failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Set new password</h1>
      <p className="text-muted-foreground mt-1 text-sm">
        Choose a strong password for your account.
      </p>

      <StatusAlert type="error" message={error} className="mt-4" />

      <form onSubmit={handleReset} className="mt-6 space-y-4">
        <div>
          <label className="text-sm text-muted-foreground">New password</label>
          <input
            className={inputClass}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            minLength={8}
            required
          />
          <PasswordStrengthChecker password={password} />
        </div>
        <div>
          <label className="text-sm text-muted-foreground">Confirm password</label>
          <input
            className={inputClass}
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="••••••••"
            minLength={8}
            required
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white py-2.5 font-medium shadow-sm shadow-emerald-500/20 disabled:opacity-60 transition-colors"
        >
          {loading ? "Resetting…" : "Reset password"}
        </button>
      </form>
    </>
  );
}

export default function ForgotPassword() {
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState("");
  const [resetToken, setResetToken] = useState("");

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

          {/* Step indicator */}
          <div className="flex gap-1.5 mb-6">
            {[1, 2, 3].map((s) => (
              <div
                key={s}
                className={`h-1 flex-1 rounded-full transition-colors ${
                  s <= step ? "bg-emerald-500" : "bg-muted"
                }`}
              />
            ))}
          </div>

          {step === 1 && (
            <StepEmail
              onSuccess={(e) => {
                setEmail(e);
                setStep(2);
              }}
            />
          )}
          {step === 2 && (
            <StepOTP
              email={email}
              onSuccess={(token) => {
                setResetToken(token);
                setStep(3);
              }}
            />
          )}
          {step === 3 && <StepNewPassword resetToken={resetToken} />}

          <div className="mt-5 text-sm text-center">
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
