"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { login, claimAnalysis, getMe, googleAuth } from "@/lib/api";
import { setToken, safeNext } from "@/lib/auth";
import PasswordInput from "@/components/PasswordInput";
import GoogleSignInButton, { GOOGLE_ENABLED } from "@/components/GoogleSignInButton";

function extractAnalysisId(next: string | null): string | null {
  if (!next) return null;
  const m = next.match(/\/results\/(\d+)/);
  return m ? m[1] : null;
}

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get("next");

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { access_token } = await login(username.trim(), password);
      setToken(access_token);

      // Claim the just-analyzed video back to this account if we came from one.
      const id = extractAnalysisId(next);
      if (id) {
        try {
          await claimAnalysis(id, access_token);
        } catch {
          // Already owned / belongs to someone else — non-fatal.
        }
      }
      // Unverified accounts must confirm their email before continuing.
      const me = await getMe(access_token).catch(() => null);
      if (me && me.email_verified === false) {
        router.push(`/verify-email?next=${encodeURIComponent(safeNext(next))}`);
        return;
      }
      router.push(safeNext(next));
    } catch {
      setError("Invalid username or password.");
      setLoading(false);
    }
  }

  async function handleGoogle(credential: string) {
    setLoading(true);
    setError("");
    try {
      const { access_token } = await googleAuth(credential);
      setToken(access_token);
      const id = extractAnalysisId(next);
      if (id) {
        try { await claimAnalysis(id, access_token); } catch { /* non-fatal */ }
      }
      router.push(safeNext(next));
    } catch {
      setError("Google sign-in failed. Please try again.");
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
          <h1 className="text-xl font-bold text-text-primary mt-4">Welcome back</h1>
          <p className="text-text-muted text-sm mt-1">Log in to your account</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="text"
            placeholder="Username or email"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoComplete="username"
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
          />
          <PasswordInput
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
          {error && <p className="text-danger text-sm">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full gradient-btn text-white font-semibold py-3 rounded-xl disabled:opacity-50"
          >
            {loading ? "Logging in…" : "Log in"}
          </button>
        </form>

        {GOOGLE_ENABLED && (
          <>
            <div className="flex items-center gap-3 text-text-muted text-xs">
              <span className="h-px flex-1 bg-border" />
              or
              <span className="h-px flex-1 bg-border" />
            </div>
            <GoogleSignInButton onCredential={handleGoogle} text="continue_with" />
          </>
        )}
        <div className="space-y-2 text-center text-sm">
          <p className="text-text-muted">
            No account?{" "}
            <Link
              href={`/signup${next ? `?next=${encodeURIComponent(next)}` : ""}`}
              className="text-accent hover:underline"
            >
              Sign up free
            </Link>
          </p>
          <p>
            <Link href="/forgot-password" className="text-accent hover:underline transition-colors">
              Forgot your password?
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
