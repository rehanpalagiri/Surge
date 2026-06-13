"use client";

import Link from "next/link";

export default function ResetPasswordPage() {
  return (
    <main className="min-h-screen flex items-center justify-center px-4 bg-background">
      <div className="w-full max-w-sm bg-card border border-border rounded-2xl p-8 space-y-6 text-center">
        <Link href="/" className="font-bold text-2xl gradient-text">Surge</Link>
        <p className="text-text-muted text-sm">
          Password reset now uses a 6-digit code.{" "}
          <Link href="/forgot-password" className="text-purple-to hover:underline">
            Reset your password here.
          </Link>
        </p>
      </div>
    </main>
  );
}
