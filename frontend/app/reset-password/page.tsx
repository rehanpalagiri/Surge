"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { resetPassword, apiErrorDetail } from "@/lib/api";

function ResetForm() {
  const router = useRouter();
  const search = useSearchParams();
  const token = search.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  if (!token) {
    return (
      <div className="space-y-4 text-center">
        <p className="text-danger">Invalid or missing reset link.</p>
        <Link href="/forgot-password" className="text-purple-to hover:underline text-sm">
          Request a new one
        </Link>
      </div>
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(apiErrorDetail(err, "Something went wrong. Please try again."));
      setLoading(false);
    }
  }

  if (done) {
    return (
      <div className="space-y-4 text-center">
        <div className="text-4xl">✅</div>
        <p className="text-text-primary font-semibold">Password updated!</p>
        <p className="text-text-muted text-sm">You can now log in with your new password.</p>
        <button
          onClick={() => router.push("/login")}
          className="w-full gradient-btn text-white font-semibold py-3 rounded-xl"
        >
          Log in
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <input
        type="password"
        placeholder="New password (min 8 characters)"
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
        disabled={loading}
        className="w-full gradient-btn text-white font-semibold py-3 rounded-xl disabled:opacity-50"
      >
        {loading ? "Saving…" : "Set new password"}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <main className="min-h-screen flex items-center justify-center px-4 bg-background">
      <div className="w-full max-w-sm bg-card border border-border rounded-2xl p-8 space-y-6">
        <div className="text-center">
          <Link href="/" className="font-bold text-2xl gradient-text">
            Surge
          </Link>
          <h1 className="text-xl font-bold text-text-primary mt-4">Set a new password</h1>
          <p className="text-text-muted text-sm mt-1">Choose something you&apos;ll remember.</p>
        </div>
        <Suspense fallback={null}>
          <ResetForm />
        </Suspense>
      </div>
    </main>
  );
}
