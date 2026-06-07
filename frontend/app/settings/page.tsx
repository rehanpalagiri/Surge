"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { getToken } from "@/lib/auth";
import { changeUsername, changePassword } from "@/lib/api";
import { THEME_KEY } from "@/components/ThemeProvider";

type Section = "account" | "appearance";

export default function SettingsPage() {
  const router = useRouter();
  const [section, setSection] = useState<Section>("account");

  // ── Guard: must be logged in ──
  useEffect(() => {
    if (!getToken()) router.push("/login?next=/settings");
  }, [router]);

  return (
    <main className="min-h-screen flex flex-col bg-background">
      <Nav subtitle="Settings" />
      <div className="max-w-2xl mx-auto w-full px-4 py-10 space-y-6">

        {/* Section tabs */}
        <div className="flex bg-card border border-border rounded-2xl p-1 gap-1 w-fit">
          {(["account", "appearance"] as Section[]).map((s) => (
            <button
              key={s}
              onClick={() => setSection(s)}
              className={`px-5 py-2 rounded-xl text-sm font-semibold capitalize transition-all ${
                section === s
                  ? "gradient-btn text-white shadow-sm"
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              {s === "account" ? "⚙️ Account" : "🎨 Appearance"}
            </button>
          ))}
        </div>

        {section === "account" && <AccountSection />}
        {section === "appearance" && <AppearanceSection />}
      </div>
    </main>
  );
}

// ─── Account ──────────────────────────────────────────────────────────────────

function AccountSection() {
  return (
    <div className="space-y-6">
      <ChangeUsernameCard />
      <ChangePasswordCard />
    </div>
  );
}

function ChangeUsernameCard() {
  const [newUsername, setNewUsername] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!newUsername.trim()) return;
    setLoading(true);
    setMsg(null);
    try {
      await changeUsername(newUsername.trim(), currentPassword);
      setMsg({ type: "ok", text: "Username updated! Log in again to refresh your session." });
      setNewUsername("");
      setCurrentPassword("");
    } catch (err: unknown) {
      const text = err instanceof Error ? err.message : "Something went wrong.";
      setMsg({ type: "err", text: text.includes("409") ? "That username is already taken." : text.includes("401") ? "Incorrect current password." : text });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
      <div>
        <h2 className="text-text-primary font-semibold text-lg">Change Username</h2>
        <p className="text-text-muted text-sm mt-0.5">Pick a new username for your account.</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <input
          type="text"
          placeholder="New username"
          value={newUsername}
          onChange={(e) => setNewUsername(e.target.value)}
          required
          className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
        />
        <input
          type="password"
          placeholder="Current password (to confirm)"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          required
          className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
        />
        {msg && (
          <p className={`text-sm ${msg.type === "ok" ? "text-success" : "text-danger"}`}>
            {msg.text}
          </p>
        )}
        <button
          type="submit"
          disabled={loading}
          className="gradient-btn text-white font-semibold px-6 py-2.5 rounded-xl disabled:opacity-50"
        >
          {loading ? "Saving…" : "Save username"}
        </button>
      </form>
    </div>
  );
}

function ChangePasswordCard() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (newPassword.length < 6) {
      setMsg({ type: "err", text: "New password must be at least 6 characters." });
      return;
    }
    setLoading(true);
    setMsg(null);
    try {
      await changePassword(currentPassword, newPassword);
      setMsg({ type: "ok", text: "Password updated successfully!" });
      setCurrentPassword("");
      setNewPassword("");
    } catch (err: unknown) {
      const text = err instanceof Error ? err.message : "Something went wrong.";
      setMsg({ type: "err", text: text.includes("401") ? "Incorrect current password." : text });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-card border border-border rounded-2xl p-6 space-y-4">
      <div>
        <h2 className="text-text-primary font-semibold text-lg">Change Password</h2>
        <p className="text-text-muted text-sm mt-0.5">Choose a strong password.</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <input
          type="password"
          placeholder="Current password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          required
          autoComplete="current-password"
          className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
        />
        <input
          type="password"
          placeholder="New password (6+ chars)"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
          autoComplete="new-password"
          className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-purple-to"
        />
        {msg && (
          <p className={`text-sm ${msg.type === "ok" ? "text-success" : "text-danger"}`}>
            {msg.text}
          </p>
        )}
        <button
          type="submit"
          disabled={loading}
          className="gradient-btn text-white font-semibold px-6 py-2.5 rounded-xl disabled:opacity-50"
        >
          {loading ? "Saving…" : "Save password"}
        </button>
      </form>
    </div>
  );
}

// ─── Appearance ───────────────────────────────────────────────────────────────

function AppearanceSection() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const saved = localStorage.getItem(THEME_KEY);
    setTheme(saved === "light" ? "light" : "dark");
  }, []);

  function applyTheme(t: "dark" | "light") {
    setTheme(t);
    localStorage.setItem(THEME_KEY, t);
    // Notify ThemeProvider and any other listeners
    window.dispatchEvent(new Event("surge-theme"));
    window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY }));
  }

  return (
    <div className="bg-card border border-border rounded-2xl p-6 space-y-5">
      <div>
        <h2 className="text-text-primary font-semibold text-lg">Appearance</h2>
        <p className="text-text-muted text-sm mt-0.5">Choose how Surge looks on your device.</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {(["dark", "light"] as const).map((t) => (
          <button
            key={t}
            onClick={() => applyTheme(t)}
            className={`flex flex-col items-center gap-3 p-5 rounded-2xl border-2 transition-all ${
              theme === t
                ? "border-purple-to bg-purple-from/10"
                : "border-border bg-surface hover:border-border/80"
            }`}
          >
            {/* Mini preview swatch */}
            <div
              className={`w-full h-14 rounded-xl border flex items-center justify-center text-sm font-semibold ${
                t === "dark"
                  ? "bg-[#0a0a0f] border-[#2a2a3d] text-[#f1f0ff]"
                  : "bg-[#f4f4ff] border-[#d8d8ee] text-[#0c0c1e]"
              }`}
            >
              Surge
            </div>
            <span className={`text-sm font-semibold capitalize ${theme === t ? "text-text-primary" : "text-text-muted"}`}>
              {t === "dark" ? "🌙 Dark" : "☀️ Light"}
            </span>
            {theme === t && (
              <span className="text-xs text-purple-to font-medium">Active</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
