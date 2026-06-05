"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { getProfile, upsertProfile, UserProfileIn } from "@/lib/api";
import { getToken } from "@/lib/auth";

const NICHES = [
  "Fitness", "Comedy", "Food", "Fashion", "Education",
  "Gaming", "Lifestyle", "Beauty", "Travel", "Business", "Other",
];

type Platform = "tiktok" | "instagram";

const PLATFORM_META: Record<Platform, { icon: string; label: string }> = {
  tiktok: { icon: "🎵", label: "TikTok" },
  instagram: { icon: "📸", label: "Instagram" },
};

interface FormState {
  handle: string;
  display_name: string;
  bio: string;
  target_audience: string;
  niche: string;
}

const EMPTY: FormState = {
  handle: "", display_name: "", bio: "", target_audience: "", niche: "Fitness",
};

export default function ProfilePage() {
  const router = useRouter();
  const [activePlatform, setActivePlatform] = useState<Platform>("tiktok");
  const [forms, setForms] = useState<Record<Platform, FormState>>({
    tiktok: { ...EMPTY },
    instagram: { ...EMPTY },
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    async function load() {
      setLoading(true);
      const [ttProf, igProf] = await Promise.all([
        getProfile("tiktok").catch(() => null),
        getProfile("instagram").catch(() => null),
      ]);
      setForms({
        tiktok: {
          handle: ttProf?.handle || "",
          display_name: ttProf?.display_name || "",
          bio: ttProf?.bio || "",
          target_audience: ttProf?.target_audience || "",
          niche: ttProf?.niche || "Fitness",
        },
        instagram: {
          handle: igProf?.handle || "",
          display_name: igProf?.display_name || "",
          bio: igProf?.bio || "",
          target_audience: igProf?.target_audience || "",
          niche: igProf?.niche || "Fitness",
        },
      });
      setLoading(false);
    }
    load();
  }, [router]);

  function update(field: keyof FormState, value: string) {
    setForms((prev) => ({
      ...prev,
      [activePlatform]: { ...prev[activePlatform], [field]: value },
    }));
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const f = forms[activePlatform];
      const data: UserProfileIn = {
        handle: f.handle.trim() || undefined,
        display_name: f.display_name.trim() || undefined,
        bio: f.bio.trim() || undefined,
        target_audience: f.target_audience.trim() || undefined,
        niche: f.niche || undefined,
      };
      await upsertProfile(activePlatform, data);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      setError("Failed to save. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  const form = forms[activePlatform];
  const meta = PLATFORM_META[activePlatform];

  return (
    <main className="min-h-screen flex flex-col bg-background">
      <Nav />
      <div className="max-w-2xl mx-auto w-full px-4 py-10 space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Creator Profiles</h1>
          <p className="text-text-muted text-sm mt-1">
            Your profile details are used to personalize every analysis. The more you fill in, the better the feedback.
          </p>
        </div>

        {/* Platform tabs */}
        <div className="flex gap-2">
          {(["tiktok", "instagram"] as Platform[]).map((p) => (
            <button
              key={p}
              onClick={() => { setActivePlatform(p); setSaved(false); setError(""); }}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all border ${
                activePlatform === p
                  ? "gradient-btn text-white border-transparent"
                  : "bg-card border-border text-text-muted hover:text-text-primary"
              }`}
            >
              {PLATFORM_META[p].icon} {PLATFORM_META[p].label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-text-muted text-sm">Loading profiles…</div>
        ) : (
          <div className="bg-card border border-border rounded-2xl p-6 space-y-5">
            <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
              {meta.icon} {meta.label} Profile
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-text-muted mb-1.5">
                  Handle
                </label>
                <input
                  type="text"
                  placeholder="@yourhandle"
                  value={form.handle}
                  onChange={(e) => update("handle", e.target.value)}
                  className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-text-muted mb-1.5">
                  Display name
                </label>
                <input
                  type="text"
                  placeholder="Your name"
                  value={form.display_name}
                  onChange={(e) => update("display_name", e.target.value)}
                  className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-text-muted mb-1.5">
                Primary niche
              </label>
              <select
                value={form.niche}
                onChange={(e) => update("niche", e.target.value)}
                className="w-full bg-card border border-border rounded-xl px-4 py-3 text-text-primary focus:outline-none focus:border-purple-to appearance-none cursor-pointer"
              >
                {NICHES.map((n) => (
                  <option key={n} value={n} className="bg-card">{n}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-text-muted mb-1.5">
                Profile bio
                <span className="text-text-muted/60 font-normal ml-1">(the bio on your {meta.label} page)</span>
              </label>
              <textarea
                placeholder={`Your ${meta.label} bio…`}
                value={form.bio}
                onChange={(e) => update("bio", e.target.value)}
                rows={3}
                maxLength={500}
                className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to resize-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-text-muted mb-1.5">
                Target audience
                <span className="text-text-muted/60 font-normal ml-1">(who you&apos;re trying to reach)</span>
              </label>
              <textarea
                placeholder="e.g. 'Women 18–25 interested in fitness and weight loss'"
                value={form.target_audience}
                onChange={(e) => update("target_audience", e.target.value)}
                rows={2}
                maxLength={300}
                className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to resize-none"
              />
            </div>

            {error && <p className="text-danger text-sm">{error}</p>}

            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={handleSave}
                disabled={saving}
                className="gradient-btn text-white font-semibold px-6 py-3 rounded-xl disabled:opacity-50"
              >
                {saving ? "Saving…" : `Save ${meta.label} Profile`}
              </button>
              {saved && (
                <span className="text-success text-sm font-medium">✓ Saved!</span>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
