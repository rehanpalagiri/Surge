"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { signup, claimAnalysis, apiErrorDetail } from "@/lib/api";
import { setToken } from "@/lib/auth";

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
  const [birthYear, setBirthYear] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const currentYear = new Date().getFullYear();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    const year = parseInt(birthYear, 10);
    if (!year || year < 1900 || year > currentYear) {
      setError("Please enter a valid birth year.");
      return;
    }
    if (currentYear - year < 13) {
      setError("You must be 13 or older to use Surge.");
      return;
    }
    if (!agreed) {
      setError("Please agree to the Terms of Service and Privacy Policy.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const { access_token } = await signup(email.trim(), username.trim(), password, year);
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
      // If coming from a results page, go back there; otherwise go to onboarding.
      if (next && next !== "/projects") {
        router.push(next);
      } else {
        router.push("/onboarding");
      }
    } catch (err: unknown) {
      setError(apiErrorDetail(err, "Could not create your account. Please try again."));
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
          <input
            type="password"
            placeholder="Password (8+ chars)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
          />
          <div>
            <input
              type="number"
              placeholder="Birth year (e.g. 1998)"
              value={birthYear}
              onChange={(e) => setBirthYear(e.target.value)}
              required
              min={1900}
              max={currentYear}
              className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
            />
            {birthYear.length === 4 && currentYear - parseInt(birthYear, 10) < 13 && (
              <p className="text-danger text-xs mt-1.5">
                You must be 13 or older to use Surge.
              </p>
            )}
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
