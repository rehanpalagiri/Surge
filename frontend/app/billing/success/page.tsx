"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { getBillingStatus } from "@/lib/api";

function SuccessInner() {
  // Checkout completed on Stripe's side. The webhook flips us to Pro a moment
  // later, so poll briefly to confirm — but show success either way (the
  // payment went through; the webhook is just the bookkeeping).
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let tries = 0;
    async function poll() {
      try {
        const s = await getBillingStatus();
        if (!cancelled && s.is_pro) {
          setConfirmed(true);
          return;
        }
      } catch {
        // ignore — keep trying
      }
      if (!cancelled && tries++ < 8) setTimeout(poll, 1500);
    }
    poll();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4">
      <div className="max-w-md w-full text-center bg-zinc-900 border border-purple-500/30 rounded-2xl p-8 shadow-xl shadow-purple-950/20">
        <div className="text-5xl mb-4">🎉</div>
        <h1 className="text-2xl font-extrabold text-white mb-2">Welcome to Surge Pro</h1>
        <p className="text-zinc-400 text-sm mb-6">
          You now have <span className="text-purple-300 font-semibold">unlimited analyses</span>.
          {confirmed ? " Your account is upgraded and ready." : " We're finalizing your account…"}
        </p>
        <div className="flex flex-col gap-2">
          <Link
            href="/"
            className="gradient-btn text-white font-semibold px-4 py-2.5 rounded-lg"
          >
            Analyze a video →
          </Link>
          <Link href="/settings" className="text-zinc-400 hover:text-white text-sm py-1">
            Manage subscription
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function BillingSuccessPage() {
  return (
    <Suspense fallback={null}>
      <SuccessInner />
    </Suspense>
  );
}
