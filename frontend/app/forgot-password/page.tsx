"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { forgotPassword, resetPassword, apiErrorDetail } from "@/lib/api";

type Step = "email" | "code" | "done";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSendCode(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await forgotPassword(email.trim().toLowerCase());
      setStep("code");
    } catch (err) {
      setError(apiErrorDetail(err, "Something went wrong. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  async function handleReset(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) { setError("Passwords don't match."); return; }
    if (password.length < 8) { setError("Password must be at least 8 characters."); return; }
    setLoading(true);
    setError("");
    try {
      await resetPassword(code.trim(), password);
      setStep("done");
    } catch (err) {
      setError(apiErrorDetail(err, "Invalid or expired code. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4 bg-background">
      <div className="w-full max-w-sm bg-card border border-border rounded-2xl p-8 space-y-6">
        <div className="text-center">
          <Link href="/" className="font-bold text-2xl gradient-text">Surge</Link>
          {step === "email" && (
            <>
              <h1 className="text-xl font-bold text-text-primary mt-4">Forgot your password?</h1>
              <p className="text-text-muted text-sm mt-1">We&apos;ll email you a 6-digit code.</p>
            </>
          )}
          {step === "code" && (
            <>
              <h1 className="text-xl font-bold text-text-primary mt-4">Enter your code</h1>
              <p className="text-text-muted text-sm mt-1">
                We sent a 6-digit code to <strong>{email}</strong>
              </p>
            </>
          )}
          {step === "done" && (
            <h1 className="text-xl font-bold text-text-primary mt-4">Password updated!</h1>
          )}
        </div>

        {step === "email" && (
          <form onSubmit={handleSendCode} className="space-y-4">
            <input
              type="email"
              placeholder="your@email.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
            />
            {error && <p className="text-danger text-sm">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full gradient-btn text-white font-semibold py-3 rounded-xl disabled:opacity-50"
            >
              {loading ? "Sending…" : "Send code"}
            </button>
            <p className="text-center">
              <Link href="/login" className="text-text-muted/60 text-sm hover:text-text-muted transition-colors">
                Back to log in
              </Link>
            </p>
          </form>
        )}

        {step === "code" && (
          <form onSubmit={handleReset} className="space-y-4">
            <input
              type="text"
              placeholder="6-digit code"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              required
              inputMode="numeric"
              maxLength={6}
              className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to text-center text-2xl tracking-widest font-bold"
            />
            <input
              type="password"
              placeholder="New password (min 8 chars)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
            />
            <input
              type="password"
              placeholder="Confirm new password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
            />
            {error && <p className="text-danger text-sm">{error}</p>}
            <button
              type="submit"
              disabled={loading || code.length !== 6}
              className="w-full gradient-btn text-white font-semibold py-3 rounded-xl disabled:opacity-50"
            >
              {loading ? "Saving…" : "Set new password"}
            </button>
            <p className="text-center text-sm">
              <button
                type="button"
                onClick={() => { setStep("email"); setError(""); setCode(""); }}
                className="text-text-muted/60 hover:text-text-muted transition-colors"
              >
                Resend code
              </button>
            </p>
          </form>
        )}

        {step === "done" && (
          <div className="space-y-4 text-center">
            <div className="text-4xl">✅</div>
            <p className="text-text-muted text-sm">You can now log in with your new password.</p>
            <button
              onClick={() => router.push("/login")}
              className="w-full gradient-btn text-white font-semibold py-3 rounded-xl"
            >
              Log in
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
