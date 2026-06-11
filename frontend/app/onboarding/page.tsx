"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { upsertProfile } from "@/lib/api";
import { Suspense } from "react";

const NICHE_SUGGESTIONS = [
  "Fitness", "Comedy", "Food", "Beauty", "Gaming",
  "Music", "Finance", "Tech", "Travel", "Lifestyle", "Fashion", "Mental Health",
];

interface ProfileForm {
  handle: string;
  display_name: string;
  bio: string;
  target_audience: string;
  niche: string;
}

const EMPTY: ProfileForm = {
  handle: "",
  display_name: "",
  bio: "",
  target_audience: "",
  niche: "",
};

const STEPS: { platform: "tiktok" | "instagram"; icon: string; label: string }[] = [
  { platform: "tiktok", icon: "🎵", label: "TikTok" },
  { platform: "instagram", icon: "📸", label: "Instagram" },
];

function OnboardingForm() {
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get("next") || "/projects";

  const [step, setStep] = useState(0);
  const [forms, setForms] = useState<Record<string, ProfileForm>>({
    tiktok: { ...EMPTY },
    instagram: { ...EMPTY },
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const current = STEPS[step];
  const form = forms[current.platform];

  function update(field: keyof ProfileForm, value: string) {
    setForms((prev) => ({
      ...prev,
      [current.platform]: { ...prev[current.platform], [field]: value },
    }));
  }

  async function handleNext() {
    setSaving(true);
    setError("");
    try {
      const f = forms[current.platform];
      // Only save if any field is filled in
      const hasData = Object.values(f).some((v) => v && v.trim());
      if (hasData) {
        await upsertProfile(current.platform, {
          handle: f.handle.trim() || undefined,
          display_name: f.display_name.trim() || undefined,
          bio: f.bio.trim() || undefined,
          target_audience: f.target_audience.trim() || undefined,
          niche: f.niche || undefined,
        });
      }
      if (step < STEPS.length - 1) {
        setStep((s) => s + 1);
      } else {
        router.push(next);
      }
    } catch {
      setError("Failed to save profile. You can update it later in Profile settings.");
      // Still advance on error — profile is optional
      if (step < STEPS.length - 1) {
        setStep((s) => s + 1);
      } else {
        router.push(next);
      }
    } finally {
      setSaving(false);
    }
  }

  function handleSkip() {
    if (step < STEPS.length - 1) {
      setStep((s) => s + 1);
    } else {
      router.push(next);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4 bg-background">
      <div className="w-full max-w-lg bg-card border border-border rounded-2xl p-8 space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <Link href="/" className="font-bold text-2xl gradient-text inline-block">
            Surge
          </Link>
          <h1 className="text-xl font-bold text-text-primary">
            Set up your creator profiles
          </h1>
          <p className="text-text-muted text-sm">
            This helps us give you personalized analysis. You can skip any field and update later.
          </p>
        </div>

        {/* Step indicators */}
        <div className="flex gap-2 justify-center">
          {STEPS.map((s, i) => (
            <div
              key={s.platform}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                i === step
                  ? "gradient-btn text-white"
                  : i < step
                  ? "bg-success/20 text-success border border-success/30"
                  : "bg-surface border border-border text-text-muted"
              }`}
            >
              {i < step ? "✓" : s.icon} {s.label}
            </div>
          ))}
        </div>

        {/* Form */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-2xl">{current.icon}</span>
            <h2 className="text-lg font-semibold text-text-primary">
              {current.label} Profile
            </h2>
          </div>

          <input
            type="text"
            placeholder={`${current.label} handle (e.g. @yourname)`}
            value={form.handle}
            onChange={(e) => update("handle", e.target.value)}
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
          />
          <input
            type="text"
            placeholder="Display name"
            value={form.display_name}
            onChange={(e) => update("display_name", e.target.value)}
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
          />
          <div>
            <label className="block text-sm font-medium text-text-muted mb-1.5">
              Primary niche
            </label>
            <input
              type="text"
              placeholder="e.g. Fitness, Comedy, Beauty…"
              value={form.niche}
              onChange={(e) => update("niche", e.target.value)}
              className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
            />
            <div className="flex flex-wrap gap-1.5 mt-2">
              {NICHE_SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => update("niche", s)}
                  className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                    form.niche === s
                      ? "bg-purple-to/15 border-purple-to/40 text-text-primary"
                      : "border-border text-text-muted hover:text-text-primary hover:border-text-muted"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          <textarea
            placeholder={`Your ${current.label} bio (the text on your profile)`}
            value={form.bio}
            onChange={(e) => update("bio", e.target.value)}
            rows={2}
            maxLength={500}
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to resize-none"
          />
          <textarea
            placeholder="Target audience (e.g. 'women 18-25 interested in fitness and weight loss')"
            value={form.target_audience}
            onChange={(e) => update("target_audience", e.target.value)}
            rows={2}
            maxLength={300}
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to resize-none"
          />
        </div>

        {error && (
          <p className="text-warning text-sm text-center">{error}</p>
        )}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={handleSkip}
            className="flex-1 border border-border text-text-muted hover:text-text-primary py-3 rounded-xl text-sm font-medium transition-colors"
          >
            Skip
          </button>
          <button
            onClick={handleNext}
            disabled={saving}
            className="flex-2 flex-grow gradient-btn text-white font-semibold py-3 px-6 rounded-xl disabled:opacity-50"
          >
            {saving
              ? "Saving…"
              : step < STEPS.length - 1
              ? `Save & Next →`
              : "Finish setup"}
          </button>
        </div>

        <p className="text-center text-text-muted text-xs">
          You can edit these any time from{" "}
          <Link href="/profile" className="text-purple-to hover:underline">
            Profile settings
          </Link>
        </p>
      </div>
    </main>
  );
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={null}>
      <OnboardingForm />
    </Suspense>
  );
}
