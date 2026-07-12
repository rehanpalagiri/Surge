"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { track } from "@vercel/analytics";
import { getToken } from "@/lib/auth";

// Set by the signup page the moment an account is created in this browser.
const LS_NEW_ACCOUNT = "surge_new_account";
// Once set, the nudge never shows again — on any page, ever.
const LS_ONBOARDED = "surge_onboarded";

/**
 * One-time, skippable nudge shown on the first arrival at the dashboard
 * after account creation: profile details (bio, audience, niche) already
 * exist at /profile and make reviews sharper, but nothing in the critical
 * path points there. Follows the UpsellModal pattern.
 */
export default function ProfileNudgeModal() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!getToken()) return;
    if (localStorage.getItem(LS_ONBOARDED)) return;
    if (!localStorage.getItem(LS_NEW_ACCOUNT)) return;
    // Persist "shown" immediately so the nudge can never fire twice, even if
    // the user navigates away without touching either button.
    localStorage.setItem(LS_ONBOARDED, "1");
    localStorage.removeItem(LS_NEW_ACCOUNT);
    track("profile_nudge_shown");
    setOpen(true);
  }, []);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4 bg-black/70 backdrop-blur-sm motion-enter"
      onClick={() => setOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Set up your creator profile"
    >
      <div
        className="relative w-full max-w-md rounded-2xl p-[1.5px] gradient-btn motion-pop"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rounded-2xl bg-card p-7 text-center">
          <button
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="absolute top-3 right-4 text-text-muted hover:text-text-primary text-2xl leading-none"
          >
            ×
          </button>

          <h2 className="text-2xl font-extrabold text-text-primary mb-3">
            Make your reviews sharper
          </h2>
          <p className="text-text-muted leading-relaxed mb-6">
            Add your bio, niche, and target audience once — every review after
            that is more personalized to your content and the people you want
            to reach.
          </p>

          <div className="flex flex-col gap-3">
            <Link
              href="/profile"
              onClick={() => track("profile_nudge_accepted")}
              className="gradient-btn font-bold py-3 rounded-xl"
            >
              Set up my profile
            </Link>
            <button
              onClick={() => setOpen(false)}
              className="text-text-muted hover:text-text-primary text-sm py-1"
            >
              Maybe later
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
