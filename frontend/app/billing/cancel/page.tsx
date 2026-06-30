"use client";

import Link from "next/link";
import UpgradeButton from "@/components/UpgradeButton";

export default function BillingCancelPage() {
  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4">
      <div className="max-w-md w-full text-center bg-zinc-900 border border-zinc-700 rounded-2xl p-8">
        <div className="text-4xl mb-4">👋</div>
        <h1 className="text-2xl font-bold text-white mb-2">Checkout canceled</h1>
        <p className="text-zinc-400 text-sm mb-6">
          No charge was made. You&apos;re still on the free plan — 3 analyses each month.
          Upgrade any time for unlimited.
        </p>
        <div className="flex flex-col items-center gap-3">
          <UpgradeButton label="Try Surge Pro again" />
          <Link href="/" className="text-zinc-400 hover:text-white text-sm">
            Back to dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
