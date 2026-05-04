import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "@/components/ui/input-otp";
import StatusAlert from "@/components/ui/StatusAlert";
import PasswordStrengthChecker from "@/components/ui/PasswordStrengthChecker";

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
      const res = await fetch("/api/auth/forgot-password", {
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
      <h1 className="text-2xl font-semibold">Forgot password</h1>
      <p className="text-slate-500 mt-1">
        Enter your email and we&apos;ll send you a reset code.
      </p>

      <StatusAlert type="error" message={error} className="mt-4" />

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <div>
          <label className="text-sm text-slate-600">Email</label>
          <input
            className="mt-1 w-full rounded-xl border px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-200"
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
          className="w-full rounded-xl bg-emerald-600 text-white py-2.5 font-medium hover:bg-emerald-700 disabled:opacity-60"
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
      const res = await fetch("/api/auth/verify-reset-otp", {
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
      const res = await fetch("/api/auth/forgot-password", {
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
      <h1 className="text-2xl font-semibold">Enter reset code</h1>

      {/* Silent-drop info banner — matches the generic backend message */}
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
          className="w-full rounded-xl bg-emerald-600 text-white py-2.5 font-medium hover:bg-emerald-700 disabled:opacity-60"
        >
          {loading ? "Verifying…" : "Verify code"}
        </button>
      </form>

      <div className="mt-5 text-sm text-slate-600 text-center">
        Didn&apos;t receive the code?{" "}
        {cooldown > 0 ? (
          <span className="text-slate-400">Resend in {cooldown}s</span>
        ) : (
          <button
            onClick={handleResend}
            disabled={loading}
            className="text-emerald-700 font-medium hover:underline disabled:opacity-60"
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
      const res = await fetch("/api/auth/reset-password", {
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
      <h1 className="text-2xl font-semibold">Set new password</h1>
      <p className="text-slate-500 mt-1">Choose a strong password for your account.</p>

      <StatusAlert type="error" message={error} className="mt-4" />

      <form onSubmit={handleReset} className="mt-6 space-y-4">
        <div>
          <label className="text-sm text-slate-600">New password</label>
          <input
            className="mt-1 w-full rounded-xl border px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-200"
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
          <label className="text-sm text-slate-600">Confirm password</label>
          <input
            className="mt-1 w-full rounded-xl border px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-200"
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
          className="w-full rounded-xl bg-emerald-600 text-white py-2.5 font-medium hover:bg-emerald-700 disabled:opacity-60"
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
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-sm border p-6">
        {/* Step indicator */}
        <div className="flex gap-1.5 mb-6">
          {[1, 2, 3].map((s) => (
            <div
              key={s}
              className={`h-1 flex-1 rounded-full transition-colors ${
                s <= step ? "bg-emerald-500" : "bg-slate-200"
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
          <Link className="text-slate-500 hover:underline" to="/login">
            Back to login
          </Link>
        </div>
      </div>
    </div>
  );
}
