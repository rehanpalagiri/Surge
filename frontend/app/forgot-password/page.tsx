"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { forgotPassword, verifyResetCode, resetPassword, apiErrorDetail } from "@/lib/api";

type Step = "email" | "code" | "password" | "done";

function OtpInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const r0 = useRef<HTMLInputElement>(null);
  const r1 = useRef<HTMLInputElement>(null);
  const r2 = useRef<HTMLInputElement>(null);
  const r3 = useRef<HTMLInputElement>(null);
  const r4 = useRef<HTMLInputElement>(null);
  const r5 = useRef<HTMLInputElement>(null);
  const refs = [r0, r1, r2, r3, r4, r5];
  // padEnd with " " (space) so we always get 6 slots; .replace(/ /g,"") strips
  // them back out when building the next state string. padEnd(6,"") is a no-op
  // per JS spec (empty padString can't lengthen the string), which would cause
  // digits=[] and make typed characters silently disappear.
  const digits = value.padEnd(6, " ").split("").slice(0, 6);

  function focus(i: number) {
    refs[i]?.current?.focus();
  }

  function handleChange(i: number, raw: string) {
    const digit = raw.replace(/\D/g, "").slice(-1);
    const next = digits.map((d, idx) => (idx === i ? digit : d)).join("").replace(/ /g, "");
    onChange(next);
    if (digit && i < 5) setTimeout(() => focus(i + 1), 0);
  }

  function handleKeyDown(i: number, e: React.KeyboardEvent) {
    if (e.key === "Backspace") {
      if (digits[i]) {
        const next = digits.map((d, idx) => (idx === i ? "" : d)).join("");
        onChange(next);
      } else if (i > 0) {
        focus(i - 1);
      }
    } else if (e.key === "ArrowLeft" && i > 0) {
      focus(i - 1);
    } else if (e.key === "ArrowRight" && i < 5) {
      focus(i + 1);
    }
  }

  function handlePaste(e: React.ClipboardEvent) {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    onChange(pasted);
    const nextIdx = Math.min(pasted.length, 5);
    setTimeout(() => focus(nextIdx), 0);
  }

  return (
    <div className="flex items-end justify-center gap-2">
      {[0, 1, 2].map((i) => (
        <input
          key={i}
          ref={refs[i]}
          type="text"
          inputMode="numeric"
          maxLength={1}
          value={digits[i] || ""}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={handlePaste}
          className="w-10 h-14 bg-transparent border-b-2 border-text-primary text-text-primary text-3xl font-bold text-center focus:outline-none focus:border-purple-to caret-transparent"
        />
      ))}
      <span className="text-text-muted text-2xl pb-2 px-1 select-none">·</span>
      {[3, 4, 5].map((i) => (
        <input
          key={i}
          ref={refs[i]}
          type="text"
          inputMode="numeric"
          maxLength={1}
          value={digits[i] || ""}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={handlePaste}
          className="w-10 h-14 bg-transparent border-b-2 border-text-primary text-text-primary text-3xl font-bold text-center focus:outline-none focus:border-purple-to caret-transparent"
        />
      ))}
    </div>
  );
}

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

  async function handleVerifyCode(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await verifyResetCode(code);
      setStep("password");
    } catch (err) {
      setError(apiErrorDetail(err, "Invalid or expired code."));
      setCode("");
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
      await resetPassword(code, password);
      setStep("done");
    } catch (err) {
      setError(apiErrorDetail(err, "Something went wrong. Please try again."));
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
              <h1 className="text-xl font-bold text-text-primary mt-4">Check your email</h1>
              <p className="text-text-muted text-sm mt-1">
                Enter the 6-digit code sent to <strong>{email}</strong>
              </p>
            </>
          )}
          {step === "password" && (
            <>
              <h1 className="text-xl font-bold text-text-primary mt-4">Set new password</h1>
              <p className="text-text-muted text-sm mt-1">Choose something you&apos;ll remember.</p>
            </>
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
            <button type="submit" disabled={loading}
              className="w-full gradient-btn text-white font-semibold py-3 rounded-xl disabled:opacity-50">
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
          <form onSubmit={handleVerifyCode} className="space-y-6">
            <OtpInput value={code} onChange={setCode} />
            {error && <p className="text-danger text-sm text-center">{error}</p>}
            <button type="submit" disabled={loading || code.length < 6}
              className="w-full gradient-btn text-white font-semibold py-3 rounded-xl disabled:opacity-50">
              {loading ? "Verifying…" : "Verify code"}
            </button>
            <p className="text-center text-sm">
              <button type="button"
                onClick={() => { setStep("email"); setError(""); setCode(""); }}
                className="text-text-muted/60 hover:text-text-muted transition-colors">
                Resend code
              </button>
            </p>
          </form>
        )}

        {step === "password" && (
          <form onSubmit={handleReset} className="space-y-4">
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
            <button type="submit" disabled={loading}
              className="w-full gradient-btn text-white font-semibold py-3 rounded-xl disabled:opacity-50">
              {loading ? "Saving…" : "Set new password"}
            </button>
          </form>
        )}

        {step === "done" && (
          <div className="space-y-4 text-center">
            <div className="text-4xl">✅</div>
            <p className="text-text-primary font-semibold">Password updated!</p>
            <p className="text-text-muted text-sm">You can now log in with your new password.</p>
            <button onClick={() => router.push("/login")}
              className="w-full gradient-btn text-white font-semibold py-3 rounded-xl">
              Log in
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
