"use client";

import { Suspense, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { signup, claimAnalysis, apiErrorDetail, googleAuth } from "@/lib/api";
import { setToken, safeNext } from "@/lib/auth";
import GoogleSignInButton, { GOOGLE_ENABLED } from "@/components/GoogleSignInButton";
import PasswordInput from "@/components/PasswordInput";
import { track } from "@vercel/analytics";

function extractAnalysisId(next: string | null): string | null {
  if (!next) return null;
  const m = next.match(/\/results\/(\d+)/);
  return m ? m[1] : null;
}

function SignupForm() {
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get("next");

  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [bMonth, setBMonth] = useState("");
  const [bDay, setBDay] = useState("");
  const [bYear, setBYear] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const dayRef = useRef<HTMLInputElement>(null);
  const yearRef = useRef<HTMLInputElement>(null);

  const dobComplete = bMonth.length >= 1 && bDay.length >= 1 && bYear.length === 4;

  function digitSetter(
    set: (v: string) => void,
    max: number,
    nextRef?: React.RefObject<HTMLInputElement | null>,
  ) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      const digits = e.target.value.replace(/\D/g, "").slice(0, max);
      set(digits);
      if (digits.length === max) nextRef?.current?.focus();
    };
  }

  function parseBirthday(): Date | null {
    if (!dobComplete) return null;
    const mm = parseInt(bMonth, 10);
    const dd = parseInt(bDay, 10);
    const yyyy = parseInt(bYear, 10);
    const d = new Date(yyyy, mm - 1, dd);
    if (isNaN(d.getTime()) || d.getMonth() !== mm - 1 || d.getDate() !== dd) return null;
    return d;
  }

  function isoBirthday(): string {
    return `${bYear}-${bMonth.padStart(2, "0")}-${bDay.padStart(2, "0")}`;
  }

  // Offer a starting username from the email — editable, never forced.
  function suggestUsername() {
    if (username.trim() || !email.includes("@")) return;
    const local = email.split("@")[0].toLowerCase().replace(/[^a-z0-9._-]/g, "").slice(0, 20);
    if (local) setUsername(local);
  }

  function calcAge(bd: Date): number {
    const today = new Date();
    let age = today.getFullYear() - bd.getFullYear();
    if (
      today.getMonth() < bd.getMonth() ||
      (today.getMonth() === bd.getMonth() && today.getDate() < bd.getDate())
    ) age--;
    return age;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !email.includes("@")) {
      setError("Enter your email address.");
      return;
    }
    if (!username.trim()) {
      setError("Pick a username — we suggested one from your email.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    const bd = parseBirthday();
    if (!bd || bd > new Date() || bd.getFullYear() < 1900) {
      setError("Please enter a valid date of birth.");
      return;
    }
    if (calcAge(bd) < 13) {
      setError("You must be 13 or older to use Surge.");
      return;
    }
    if (!agreed) {
      setError("Please agree to the Terms of Service and Privacy Policy.");
      return;
    }
    setLoading(true);
    setError("");
    const isoDate = isoBirthday();
    try {
      const { access_token } = await signup(email.trim(), username.trim(), password, isoDate);
      setToken(access_token);
      // Marks this browser as a brand-new account so the dashboard can show
      // the one-time profile nudge (ProfileNudgeModal consumes this).
      localStorage.setItem("surge_new_account", "1");

      // Save the just-analyzed video to the brand-new account.
      const id = extractAnalysisId(next);
      if (id) {
        try {
          await claimAnalysis(id, access_token);
        } catch {
          // Non-fatal.
        }
      }
      track("signup_complete", { from_results: !!extractAnalysisId(next) });
      // New accounts must confirm their email first. The verify page continues
      // to `next` (or /projects) once the 6-digit code checks out.
      const dest = safeNext(next, "/projects");
      router.push(`/verify-email?next=${encodeURIComponent(dest)}`);
    } catch (err: unknown) {
      setError(apiErrorDetail(err, "Could not create your account. Please try again."));
      setLoading(false);
    }
  }

  // Google sign-up. We require a valid 13+ DOB first (the field above) so the
  // age gate still applies; Google-verified email means no code step.
  async function handleGoogle(credential: string) {
    const bd = parseBirthday();
    if (!bd || bd > new Date() || bd.getFullYear() < 1900 || calcAge(bd) < 13) {
      setError("Enter your date of birth above first, then continue with Google.");
      return;
    }
    const isoDate = isoBirthday();
    setLoading(true);
    setError("");
    try {
      const { access_token } = await googleAuth(credential, isoDate);
      setToken(access_token);
      localStorage.setItem("surge_new_account", "1");
      const id = extractAnalysisId(next);
      if (id) {
        try { await claimAnalysis(id, access_token); } catch { /* non-fatal */ }
      }
      track("signup_complete", { from_results: !!extractAnalysisId(next), method: "google" });
      // Google verifies the email, so skip the code step.
      const dest = safeNext(next, "/projects");
      router.push(dest);
    } catch (err: unknown) {
      setError(apiErrorDetail(err, "Google sign-in failed. Please try again."));
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4 bg-background">
      <div className="w-full max-w-sm bg-card border border-border rounded-2xl p-8 space-y-6">
        <div className="text-center">
          <Link href="/" className="font-bold text-2xl gradient-text">
            Surge
          </Link>
          <h1 className="text-xl font-bold text-text-primary mt-4">
            Create your free account
          </h1>
          <p className="text-text-muted text-sm mt-1">
            Unlock your full improvement plan
          </p>
        </div>
        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onBlur={suggestUsername}
            required
            autoComplete="email"
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
          />
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoComplete="username"
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
          />
          <PasswordInput
            placeholder="Password (8+ chars)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
          />
          <fieldset className="min-w-0 [min-inline-size:0]">
            <legend className="text-text-muted text-xs font-medium mb-1.5">Date of birth</legend>
            <div className="flex gap-2">
              <input
                type="text"
                inputMode="numeric"
                placeholder="MM"
                aria-label="Birth month"
                value={bMonth}
                onChange={digitSetter(setBMonth, 2, dayRef)}
                required
                maxLength={2}
                autoComplete="bday-month"
                className="w-16 text-center bg-surface border border-border rounded-xl px-2 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
              />
              <input
                ref={dayRef}
                type="text"
                inputMode="numeric"
                placeholder="DD"
                aria-label="Birth day"
                value={bDay}
                onChange={digitSetter(setBDay, 2, yearRef)}
                required
                maxLength={2}
                autoComplete="bday-day"
                className="w-16 text-center bg-surface border border-border rounded-xl px-2 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
              />
              <input
                ref={yearRef}
                type="text"
                inputMode="numeric"
                placeholder="YYYY"
                aria-label="Birth year"
                value={bYear}
                onChange={digitSetter(setBYear, 4)}
                required
                maxLength={4}
                autoComplete="bday-year"
                className="flex-1 min-w-0 text-center bg-surface border border-border rounded-xl px-2 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
              />
            </div>
            {dobComplete && (() => {
              const bd = parseBirthday();
              if (!bd) {
                return <p className="text-danger text-xs mt-1.5">That date doesn&apos;t exist — double-check it.</p>;
              }
              if (calcAge(bd) < 13) {
                return <p className="text-danger text-xs mt-1.5">You must be 13 or older to use Surge.</p>;
              }
              return null;
            })()}
          </fieldset>
          <label className="flex items-start gap-2.5 cursor-pointer">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              required
              className="mt-0.5 accent-accent"
            />
            <span className="text-text-muted text-xs leading-relaxed">
              I agree to Surge&apos;s{" "}
              <Link href="/terms" target="_blank" className="text-accent hover:underline">
                Terms of Service
              </Link>{" "}
              and{" "}
              <Link href="/privacy" target="_blank" className="text-accent hover:underline">
                Privacy Policy
              </Link>
            </span>
          </label>
          {error && <p className="text-danger text-sm">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full gradient-btn text-white font-semibold py-3 rounded-xl disabled:opacity-50"
          >
            {loading ? "Creating account…" : "Sign up free"}
          </button>
        </form>

        {GOOGLE_ENABLED && (
          <>
            <div className="flex items-center gap-3 text-text-muted text-xs">
              <span className="h-px flex-1 bg-border" />
              or
              <span className="h-px flex-1 bg-border" />
            </div>
            <GoogleSignInButton onCredential={handleGoogle} text="signup_with" />
          </>
        )}
        <p className="text-text-muted text-sm text-center">
          Already have an account?{" "}
          <Link
            href={`/login${next ? `?next=${encodeURIComponent(next)}` : ""}`}
            className="text-accent hover:underline"
          >
            Log in
          </Link>
        </p>
      </div>
    </main>
  );
}

export default function SignupPage() {
  return (
    <Suspense fallback={null}>
      <SignupForm />
    </Suspense>
  );
}
