"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check } from "lucide-react";
import Nav from "@/components/Nav";
import UpgradeButton from "@/components/UpgradeButton";
import { getBillingStatus, BillingStatus } from "@/lib/api";
import { getToken } from "@/lib/auth";

const FALLBACK_PRICE = "$9.99/mo";

const FREE_FEATURES = [
  "3 craft reviews a month",
  "Earn +1 review per linked post (up to +10)",
  "The full report — six dimensions, risk map, next experiment",
  "Craft vs. Your Results insights",
  "No card required",
];

const PRO_FEATURES = [
  "Unlimited craft reviews",
  "Everything in Free — same full report",
  "Review every draft, not just the final cut",
  "Cancel anytime from Settings",
];

export default function PricingPage() {
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);
  const [billing, setBilling] = useState<BillingStatus | null>(null);

  useEffect(() => {
    const authed = !!getToken();
    setLoggedIn(authed);
    if (authed) {
      getBillingStatus().then(setBilling).catch(() => {});
    }
  }, []);

  const price = billing?.price || FALLBACK_PRICE;
  const isPro = billing?.is_pro ?? false;
  const configured = billing?.configured ?? false;

  return (
    <main className="min-h-screen bg-background">
      <Nav subtitle="Pricing" />

      <div className="max-w-4xl mx-auto px-4 py-12 space-y-10">
        <div className="text-center space-y-3">
          <h1 className="text-3xl sm:text-4xl font-extrabold text-text-primary">
            Simple <span className="gradient-text">honest</span> pricing
          </h1>
          <p className="text-text-muted max-w-xl mx-auto">
            Same analysis depth on both plans — Pro removes the monthly cap.
            No tier ever gets a fake viral score.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-3xl mx-auto">
          {/* ── Free ── */}
          <div className="bg-card border border-border rounded-2xl p-7 flex flex-col gap-6">
            <div>
              <h2 className="text-text-primary font-bold text-lg">Free</h2>
              <p className="mt-2">
                <span className="text-4xl font-extrabold text-text-primary">$0</span>
                <span className="text-text-muted text-sm"> / forever</span>
              </p>
            </div>
            <ul className="space-y-2.5 flex-1">
              {FREE_FEATURES.map((f) => (
                <li key={f} className="flex items-start gap-2.5 text-sm text-text-muted">
                  <Check className="h-4 w-4 mt-0.5 flex-shrink-0 text-success" />
                  {f}
                </li>
              ))}
            </ul>
            {loggedIn ? (
              <Link
                href="/"
                className="btn-soft text-text-primary font-semibold py-3 rounded-xl text-center text-sm"
              >
                {isPro ? "Included in your plan" : "You're on Free — review a video"}
              </Link>
            ) : (
              <Link
                href="/signup"
                className="btn-soft text-text-primary font-semibold py-3 rounded-xl text-center text-sm"
              >
                Start free
              </Link>
            )}
          </div>

          {/* ── Pro ── */}
          <div className="bg-card border-2 border-accent/40 rounded-2xl p-7 flex flex-col gap-6 relative">
            <span className="absolute -top-3 left-7 bg-accent text-white text-[11px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full">
              Surge Pro
            </span>
            <div>
              <h2 className="text-text-primary font-bold text-lg">Pro</h2>
              <p className="mt-2">
                <span className="text-4xl font-extrabold text-text-primary">
                  {price.replace(/\/mo$/, "")}
                </span>
                <span className="text-text-muted text-sm"> / month</span>
              </p>
            </div>
            <ul className="space-y-2.5 flex-1">
              {PRO_FEATURES.map((f) => (
                <li key={f} className="flex items-start gap-2.5 text-sm text-text-muted">
                  <Check className="h-4 w-4 mt-0.5 flex-shrink-0 text-accent" />
                  {f}
                </li>
              ))}
            </ul>

            {loggedIn === null ? (
              <div className="h-12 rounded-xl skeleton" />
            ) : !loggedIn ? (
              <Link
                href="/signup?next=/pricing"
                className="gradient-btn text-white font-bold py-3 rounded-xl text-center"
              >
                Sign up, then go Pro
              </Link>
            ) : isPro ? (
              <Link
                href="/settings"
                className="btn-soft text-text-primary font-semibold py-3 rounded-xl text-center text-sm"
              >
                You&apos;re on Pro — manage in Settings
              </Link>
            ) : configured ? (
              <UpgradeButton
                label={`Go unlimited — ${price}`}
                className="gradient-btn text-white font-bold py-3 rounded-xl w-full"
              />
            ) : (
              <div className="space-y-2">
                <button
                  disabled
                  className="w-full border border-border text-text-muted font-semibold py-3 rounded-xl text-sm cursor-not-allowed"
                >
                  Billing opens soon
                </button>
                <p className="text-text-muted text-xs text-center">
                  Pro checkout isn&apos;t live yet — the free plan is, today.
                </p>
              </div>
            )}
          </div>
        </div>

        <p className="text-text-muted/80 text-xs text-center max-w-lg mx-auto">
          Reviews are AI assessments of observable craft — never a promise of reach.
          Free quota resets on the 1st of each month (UTC). Linked-post bonus reviews
          stack on top of the monthly 3.
        </p>
      </div>
    </main>
  );
}
