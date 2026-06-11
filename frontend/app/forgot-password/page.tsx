"use client";

import { useState } from "react";
import Link from "next/link";
import { forgotPassword, apiErrorDetail } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await forgotPassword(email.trim().toLowerCase());
      setSent(true);
    } catch (err) {
      setError(apiErrorDetail(err, "Something went wrong. Please try again."));
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
          <h1 className="text-xl font-bold text-text-primary mt-4">Forgot your password?</h1>
          <p className="text-text-muted text-sm mt-1">
            Enter your email and we&apos;ll send a reset link.
          </p>
        </div>

        {sent ? (
          <div className="space-y-4 text-center">
            <div className="text-4xl">📬</div>
            <p className="text-text-primary font-semibold">Check your inbox</p>
            <p className="text-text-muted text-sm">
              If an account exists for <strong>{email}</strong>, a reset link is on its way.
              It expires in 1 hour.
            </p>
            <Link
              href="/login"
              className="block w-full bg-surface border border-border text-text-primary font-semibold py-3 rounded-xl text-center hover:border-purple-to/50 transition-colors"
            >
              Back to log in
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
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
              {loading ? "Sending…" : "Send reset link"}
            </button>
            <p className="text-center">
              <Link href="/login" className="text-text-muted/60 text-sm hover:text-text-muted transition-colors">
                Back to log in
              </Link>
            </p>
          </form>
        )}
      </div>
    </main>
  );
}
