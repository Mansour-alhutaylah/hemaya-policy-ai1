import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "@/components/ui/input-otp";

export default function VerifyOTP() {
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const email = searchParams.get("email") || "";

  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  // 60-second cooldown mirrors the server-side rate limit.
  // Start immediately because an OTP was just sent at registration.
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
      const res = await fetch("/api/auth/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Verification failed");
      setSuccess("Email verified! Redirecting to login…");
      setTimeout(() => nav("/login"), 1500);
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
      const res = await fetch("/api/auth/resend-otp", {
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
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-sm border p-6">
        <h1 className="text-2xl font-semibold">Verify your email</h1>
        <p className="text-slate-500 mt-1">
          Enter the 6-digit code sent to{" "}
          <span className="font-medium text-slate-700">{email}</span>
        </p>

        {error && (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {success && (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
            {success}
          </div>
        )}

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
            className="w-full rounded-xl bg-emerald-600 text-white py-2.5 font-medium hover:bg-emerald-700 disabled:opacity-60"
          >
            {loading ? "Verifying…" : "Verify email"}
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

        <div className="mt-3 text-sm text-center">
          <Link className="text-slate-500 hover:underline" to="/login">
            Back to login
          </Link>
        </div>
      </div>
    </div>
  );
}
