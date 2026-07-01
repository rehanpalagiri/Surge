"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { signup, claimAnalysis, apiErrorDetail, googleAuth } from "@/lib/api";
import { setToken } from "@/lib/auth";
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
  const [birthday, setBirthday] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function handleBirthdayChange(e: React.ChangeEvent<HTMLInputElement>) {
    const digits = e.target.value.replace(/\D/g, "").slice(0, 8);
    let formatted = digits;
    if (digits.length > 2) formatted = `${digits.slice(0, 2)}/${digits.slice(2)}`;
    if (digits.length > 4) formatted = `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
    setBirthday(formatted);
  }

  function parseBirthday(): Date | null {
    const parts = birthday.split("/");
    if (parts.length !== 3) return null;
    const [mm, dd, yyyy] = parts;
    if (yyyy.length < 4) return null;
    const d = new Date(parseInt(yyyy), parseInt(mm) - 1, parseInt(dd));
    if (isNaN(d.getTime()) || d.getMonth() !== parseInt(mm) - 1) return null;
    return d;
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
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    const bd = parseBirthday();
    if (!bd || bd > new Date() || bd.getFullYear() < 1900) {
      setError("Please enter a valid date of birth (MM/DD/YYYY).");
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
    const [mm, dd, yyyy] = birthday.split("/");
    const isoDate = `${yyyy}-${mm.padStart(2, "0")}-${dd.padStart(2, "0")}`;
    try {
      const { access_token } = await signup(email.trim(), username.trim(), password, isoDate);
      setToken(access_token);

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
      const dest = next && next !== "/projects" ? next : "/projects";
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
    const [mm, dd, yyyy] = birthday.split("/");
    const isoDate = `${yyyy}-${mm.padStart(2, "0")}-${dd.padStart(2, "0")}`;
    setLoading(true);
    setError("");
    try {
      const { access_token } = await googleAuth(credential, isoDate);
      setToken(access_token);
      const id = extractAnalysisId(next);
      if (id) {
        try { await claimAnalysis(id, access_token); } catch { /* non-fatal */ }
      }
      track("signup_complete", { from_results: !!extractAnalysisId(next), method: "google" });
      // Google verifies the email, so skip the code step.
      const dest = next && next !== "/projects" ? next : "/projects";
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
        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
          />
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoComplete="username"
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
          />
          <PasswordInput
            placeholder="Password (8+ chars)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
          />
          <div>
            <input
              type="text"
              inputMode="numeric"
              placeholder="Birthday (MM/DD/YYYY)"
              value={birthday}
              onChange={handleBirthdayChange}
              required
              maxLength={10}
              className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
            />
            {birthday.length === 10 && (() => {
              const bd = parseBirthday();
              if (bd && calcAge(bd) < 13) {
                return <p className="text-danger text-xs mt-1.5">You must be 13 or older to use Surge.</p>;
              }
              return null;
            })()}
          </div>
          <label className="flex items-start gap-2.5 cursor-pointer">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              required
              className="mt-0.5 accent-purple-500"
            />
            <span className="text-text-muted text-xs leading-relaxed">
              I agree to Surge&apos;s{" "}
              <Link href="/terms" target="_blank" className="text-purple-to hover:underline">
                Terms of Service
              </Link>{" "}
              and{" "}
              <Link href="/privacy" target="_blank" className="text-purple-to hover:underline">
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
            className="text-purple-to hover:underline"
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
