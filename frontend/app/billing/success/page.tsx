"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { getBillingStatus, getCheckoutSessionStatus } from "@/lib/api";

type Phase =
  | "verifying"
  | "paid_pending"
  | "confirmed"
  | "not_completed"
  | "unverified";

function SuccessInner() {
  const params = useSearchParams();
  const sessionId = params.get("session_id");
  const [phase, setPhase] = useState<Phase>(
    sessionId ? "verifying" : "unverified"
  );

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    let tries = 0;

    async function poll() {
      try {
        const [checkout, billing] = await Promise.all([
          getCheckoutSessionStatus(sessionId!),
          getBillingStatus(),
        ]);
        if (cancelled) return;

        const paid =
          checkout.payment_status === "paid" ||
          checkout.payment_status === "no_payment_required";
        if (paid && billing.is_pro) {
          setPhase("confirmed");
          return;
        }
        if (paid && checkout.status === "complete") {
          setPhase("paid_pending");
        } else if (checkout.status === "expired") {
          setPhase("not_completed");
          return;
        }
      } catch {
        if (!cancelled && tries >= 8) setPhase("unverified");
      }

      if (!cancelled && tries++ < 8) {
        window.setTimeout(poll, 1500);
      }
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const confirmed = phase === "confirmed";
  const pending = phase === "paid_pending" || phase === "verifying";
  const title = confirmed
    ? "Welcome to CraftLint Pro"
    : phase === "paid_pending"
    ? "Payment received"
    : phase === "verifying"
    ? "Verifying your payment…"
    : phase === "not_completed"
    ? "Checkout was not completed"
    : "We couldn’t verify this checkout";

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4">
      <div className="max-w-md w-full text-center bg-card border border-accent/30 rounded-2xl p-8 shadow-xl shadow-black/5">
        <div className="text-5xl mb-4">{confirmed ? "🎉" : pending ? "•••" : "!"}</div>
        <h1 className="text-2xl font-extrabold text-text-primary mb-2">{title}</h1>
        <p className="text-text-muted text-sm mb-6">
          {confirmed
            ? "Your account is upgraded with unlimited analyses."
            : phase === "paid_pending"
            ? "Stripe confirmed the payment. We’re waiting for the signed webhook to activate Pro."
            : phase === "verifying"
            ? "This normally takes only a few seconds."
            : "No Pro access was granted from this page. Check Settings or start checkout again."}
        </p>
        <div className="flex flex-col gap-2">
          <Link
            href={confirmed ? "/" : "/settings"}
            className="gradient-btn text-white font-semibold px-4 py-2.5 rounded-lg"
          >
            {confirmed ? "Analyze a video →" : "Check billing status →"}
          </Link>
          {!confirmed && (
            <Link href="/pricing" className="text-text-muted hover:text-text-primary text-sm py-1">
              Return to pricing
            </Link>
          )}
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
