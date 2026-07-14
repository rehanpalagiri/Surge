"use client";

import Link from "next/link";
import BrandLogo from "@/components/BrandLogo";

export default function ResetPasswordPage() {
  return (
    <main className="min-h-screen flex items-center justify-center px-4 bg-background">
      <div className="w-full max-w-sm bg-card border border-border rounded-2xl p-8 space-y-6 text-center">
        <BrandLogo className="text-2xl" />
        <p className="text-text-muted text-sm">
          Password reset now uses a 6-digit code.{" "}
          <Link href="/forgot-password" className="text-accent hover:underline">
            Reset your password here.
          </Link>
        </p>
      </div>
    </main>
  );
}
