"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { signup, claimAnalysis } from "@/lib/api";
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

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const { access_token } = await signup(username.trim(), password);
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
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("409")) {
        setError("That username is already taken.");
      } else {
        setError("Could not create your account. Try a different username.");
      }
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
            placeholder="Password (6+ chars)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
          />
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
