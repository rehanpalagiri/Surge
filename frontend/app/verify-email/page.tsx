"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { getMe, verifyEmail, resendVerification, apiErrorDetail } from "@/lib/api";
import { getToken, clearToken } from "@/lib/auth";
import OtpInput from "@/components/OtpInput";

function VerifyEmailInner() {
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get("next");
  const dest = next && next.startsWith("/") ? next : "/projects";

  const [email, setEmail] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [resent, setResent] = useState(false);

  // Guard: must be signed in. If already verified, skip straight through.
  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    getMe(token)
      .then((u) => {
        if (u.email_verified) router.replace(dest);
        else setEmail(u.email ?? null);
      })
      .catch(() => {
        clearToken();
        router.replace("/login");
      });
  }, [router, dest]);

  async function submit(value: string) {
    setLoading(true);
    setError("");
    try {
      await verifyEmail(value, getToken());
      router.replace(dest);
    } catch (err: unknown) {
      setError(apiErrorDetail(err, "Invalid or expired code. Try again or resend a new one."));
      setLoading(false);
    }
  }

  function handleChange(v: string) {
    setCode(v);
    setError("");
    if (v.length === 6) submit(v);  // auto-submit once all six digits are in
  }

  async function handleResend() {
    setError("");
    setResent(false);
    try {
      await resendVerification(getToken());
      setResent(true);
    } catch (err: unknown) {
      setError(apiErrorDetail(err, "Couldn't resend right now. Please wait a moment."));
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-background px-4">
      <div className="w-full max-w-md bg-card border border-border rounded-2xl p-8 motion-enter">
        <h1 className="text-2xl font-bold text-text-primary text-center">Confirm your email</h1>
        <p className="text-text-muted text-sm mt-2 text-center">
          We sent a 6-digit code to{" "}
          <strong className="text-text-primary">{email ?? "your email"}</strong>. Enter it below.
        </p>

        <div className="my-7">
          <OtpInput value={code} onChange={handleChange} />
        </div>

        {error && <p className="text-danger text-sm text-center mb-3">{error}</p>}

        <button
          type="button"
          disabled={loading || code.length < 6}
          onClick={() => submit(code)}
          className="gradient-btn w-full text-white font-semibold py-3 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Verifying…" : "Verify email"}
        </button>

        <div className="mt-5 text-center text-sm text-text-muted">
          {resent ? (
            <span className="text-success">New code sent — check your inbox.</span>
          ) : (
            <>
              Didn&apos;t get it?{" "}
              <button type="button" onClick={handleResend} className="text-purple-to hover:underline">
                Resend code
              </button>
            </>
          )}
        </div>

        <div className="mt-4 flex items-center justify-center gap-3 text-xs text-text-muted">
          {/* Escape hatch: verification isn't required to use Surge, so a user
              whose code is delayed or undelivered is never trapped here. */}
          <button type="button" onClick={() => router.replace(dest)} className="hover:text-text-primary">
            Skip for now →
          </button>
          <span aria-hidden className="text-border">|</span>
          <Link href="/login" onClick={() => clearToken()} className="hover:text-text-primary">
            Use a different account
          </Link>
        </div>
      </div>
    </main>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailInner />
    </Suspense>
  );
}
