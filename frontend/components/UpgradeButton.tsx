"use client";

import { useState } from "react";
import { createCheckoutSession, apiErrorDetail } from "@/lib/api";

/**
 * Starts a Surge Pro subscription: calls our backend to create a Stripe Checkout
 * Session, then redirects to the hosted checkout page. Never talks to Stripe
 * directly from the browser.
 */
export default function UpgradeButton({
  className,
  children,
  label = "Upgrade to Surge Pro",
}: {
  className?: string;
  children?: React.ReactNode;
  label?: string;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function go() {
    setLoading(true);
    setError("");
    try {
      const { url } = await createCheckoutSession();
      window.location.href = url; // → Stripe hosted checkout
    } catch (err) {
      setError(apiErrorDetail(err, "Couldn't start checkout. Please try again."));
      setLoading(false);
    }
  }

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={go}
        disabled={loading}
        className={
          className ??
          "gradient-btn text-white font-semibold px-4 py-2 rounded-lg disabled:opacity-60"
        }
      >
        {loading ? "Starting checkout…" : children ?? label}
      </button>
      {error && <span className="text-red-400 text-[11px]">{error}</span>}
    </span>
  );
}
