"use client";

import { useState, useEffect, useCallback, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import PasswordInput from "@/components/PasswordInput";
import { getToken, clearToken, setToken } from "@/lib/auth";
import { changeUsername, changePassword, deleteAccount, getConsent, updateConsent, ConsentStatus, getBillingStatus, createPortalSession, BillingStatus, apiErrorDetail } from "@/lib/api";
import { SettingsPrivacySkeleton, SettingsSkeleton } from "@/components/Skeleton";
import UpgradeButton from "@/components/UpgradeButton";

function ProfileCard() {
  return (
    <div className="bg-card border border-border rounded-2xl p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-text-primary font-semibold text-lg">Profile</h2>
          <p className="text-text-muted text-sm mt-0.5">Manage your public handle and display name.</p>
        </div>
        <Link
          href="/profile"
          className="gradient-btn text-white font-semibold px-5 py-2 rounded-xl transition-colors text-sm"
        >
          Edit profile
        </Link>
      </div>
    </div>
  );
}

function BillingCard() {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [portalBusy, setPortalBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getBillingStatus()
      .then(setStatus)
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  async function openPortal() {
    setPortalBusy(true);
    setError("");
    try {
      const { url } = await createPortalSession();
      window.location.href = url;
    } catch (err) {
      setError(apiErrorDetail(err, "Couldn't open the billing portal. Please try again."));
      setPortalBusy(false);
    }
  }

  if (!loaded || !status) return null;

  // Billing not configured yet (Stripe keys unset): show the plan honestly
  // and point at the pricing page instead of a dead checkout.
  if (!status.configured) {
    return (
      <div className="bg-card border border-border rounded-2xl p-6">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-text-primary font-semibold text-lg">Plan</h2>
            <p className="text-text-muted text-sm mt-0.5">
              Free plan — 3 analyses a month, plus earn-by-linking bonuses.
            </p>
          </div>
          <Link
            href="/pricing"
            className="border border-border text-text-primary font-semibold px-5 py-2 rounded-xl hover:border-accent/50 transition-colors text-sm"
          >
            See plans →
          </Link>
        </div>
      </div>
    );
  }

  const renews = status.current_period_end
    ? new Date(status.current_period_end).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
    : null;

  return (
    <div className="bg-card border border-border rounded-2xl p-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-text-primary font-semibold text-lg flex items-center gap-2">
            {status.is_pro ? <>CraftLint Pro <span className="text-accent">✦</span></> : "Plan"}
          </h2>
          {status.comp ? (
            <p className="text-text-muted text-sm mt-0.5">
              Complimentary Pro — unlimited analyses, no billing.
            </p>
          ) : status.is_pro ? (
            <p className="text-text-muted text-sm mt-0.5">
              Unlimited analyses.
              {status.subscription_status === "past_due"
                ? " ⚠ Last payment failed — please update your card."
                : status.cancel_at_period_end && renews
                ? ` Your subscription ends ${renews}.`
                : renews
                ? ` Renews ${renews}.`
                : ""}
            </p>
          ) : !status.eligible_for_paid ? (
            <p className="text-text-muted text-sm mt-0.5">
              Free plan — paid subscriptions are available to users 18 or older.
            </p>
          ) : (
            <p className="text-text-muted text-sm mt-0.5">
              Free plan — 3 analyses per month. Upgrade to {status.price} for unlimited.
            </p>
          )}
        </div>
        {status.comp ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-bold text-accent">
            ✦ Complimentary
          </span>
        ) : status.is_pro ? (
          <button
            onClick={openPortal}
            disabled={portalBusy}
            className="border border-border text-text-primary font-semibold px-5 py-2 rounded-xl hover:border-text-muted/60 transition-colors text-sm disabled:opacity-60"
          >
            {portalBusy ? "Opening…" : "Manage subscription"}
          </button>
        ) : status.eligible_for_paid ? (
          <UpgradeButton label="Upgrade to Pro" />
        ) : (
          <span className="text-text-muted text-xs font-medium">
            Adults only
          </span>
        )}
      </div>
      {error && <p className="text-danger text-xs mt-3">{error}</p>}
    </div>
  );
}

function LogOutCard() {
  const router = useRouter();

  function handleLogOut() {
    clearToken();
    router.push("/");
  }

  return (
    <div className="bg-card border border-border rounded-2xl p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-text-primary font-semibold text-lg">Log out</h2>
          <p className="text-text-muted text-sm mt-0.5">Sign out of your account on this device.</p>
        </div>
        <button
          onClick={handleLogOut}
          className="border border-border text-text-primary font-semibold px-5 py-2 rounded-xl hover:border-text-muted/60 transition-colors text-sm"
        >
          Log out
        </button>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login?next=/settings");
      return;
    }
    setAuthReady(true);
  }, [router]);

  return (
    <main className="min-h-screen flex flex-col bg-background">
      <Nav subtitle="Settings" />
      <div className="max-w-2xl mx-auto w-full px-4 py-10 space-y-10">
        {!authReady ? <SettingsSkeleton /> : (
          <>
            <SettingsSection title="Account">
              <ProfileCard />
              <ChangeUsernameCard />
              <ChangePasswordCard />
            </SettingsSection>

            <SettingsSection title="Plan">
              <BillingCard />
            </SettingsSection>

            <SettingsSection title="Privacy">
              <DataPrivacyCard />
            </SettingsSection>

            <SettingsSection title="Session">
              <LogOutCard />
            </SettingsSection>

            <SettingsSection title="Danger zone">
              <DeleteAccountCard />
            </SettingsSection>
          </>
        )}
        <p className="text-center text-text-muted/60 text-xs pt-2">
          <Link href="/privacy" className="hover:text-text-muted transition-colors">Privacy Policy</Link>
          <span className="mx-2">·</span>
          <Link href="/terms" className="hover:text-text-muted transition-colors">Terms of Service</Link>
        </p>
      </div>
    </main>
  );
}

function SettingsSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="mb-3 text-xs font-bold uppercase tracking-wider text-text-muted">{title}</h2>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

const CONSENT_OPTIONS: { value: "yes" | "ask" | "no"; label: string }[] = [
  { value: "yes", label: "Yes — my linked public metrics can be retained for measurement research" },
  { value: "ask", label: "Ask me each time — I'll decide when I link a video" },
  { value: "no", label: "No — do not retain my metrics for research" },
];

function DataPrivacyCard() {
  const [consent, setConsent] = useState<ConsentStatus | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const loadConsent = useCallback(async () => {
    setConsent(null);
    setLoadFailed(false);
    try {
      setConsent(await getConsent());
    } catch {
      setLoadFailed(true);
    }
  }, []);

  useEffect(() => { void loadConsent(); }, [loadConsent]);

  async function pick(value: "yes" | "no" | "ask") {
    if (!consent || consent.is_minor || saving) return;
    const prev = consent;
    setConsent({ ...consent, seed_consent: value });
    setSaving(true);
    setError("");
    try {
      await updateConsent(value);
    } catch {
      setConsent(prev);
      setError("Couldn't save your preference — please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="bg-card border border-border rounded-2xl p-6 space-y-4" aria-busy={saving}>
      <div>
        <h2 className="text-text-primary font-semibold text-lg">Data &amp; Privacy</h2>
        <p className="text-text-muted text-sm mt-0.5">Choose whether linked public metrics may support measurement research</p>
      </div>

      {!consent && loadFailed ? (
        <div className="rounded-xl border border-danger/30 bg-danger/5 p-4 space-y-3">
          <p className="text-danger text-sm" role="alert">
            Couldn&apos;t load your privacy preference. Your existing choice has not changed.
          </p>
          <button
            type="button"
            onClick={() => void loadConsent()}
            className="border border-border text-text-primary text-sm font-semibold px-4 py-2 rounded-lg hover:border-accent/60"
          >
            Try again
          </button>
        </div>
      ) : !consent ? (
        <SettingsPrivacySkeleton />
      ) : consent.is_minor ? (
        <p className="text-text-muted text-sm">
          Your data is not used for measurement research (accounts under 18 are
          automatically excluded).
        </p>
      ) : (
        <>
          <div className="space-y-2">
            {CONSENT_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                  consent.seed_consent === opt.value
                    ? "border-accent/50 bg-accent/5"
                    : "border-border hover:border-text-muted/40"
                }`}
              >
                <input
                  type="radio"
                  name="seed_consent"
                  checked={consent.seed_consent === opt.value}
                  onChange={() => pick(opt.value)}
                  className="mt-0.5 accent-accent"
                />
                <span className="text-text-primary text-sm">{opt.label}</span>
              </label>
            ))}
          </div>
          {error && <p className="text-danger text-sm">{error}</p>}
          {saving && <p className="text-text-muted text-xs" role="status"><span className="pending-spinner mr-1.5 align-[-0.1em]" aria-hidden="true" />Saving preference…</p>}
          <p className="text-text-muted/60 text-xs">
            Research data may include public counts, observation time, post URL, and content niche—never
            your uploaded video. Metrics are not treated as proof that an edit caused an outcome.{" "}
            <Link href="/privacy#seed-pool" className="text-accent hover:underline">
              Learn more
            </Link>
          </p>
        </>
      )}
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
      setMsg({ type: "ok", text: "Username updated!" });
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
          autoComplete="username"
          className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
        />
        <label className="block">
          <span className="block text-text-muted text-xs font-medium mb-1.5">
            Confirm with your password
          </span>
          <PasswordInput
            placeholder="Current password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </label>
        <Link href="/forgot-password" className="block text-accent text-sm hover:underline">
          Forgot your password?
        </Link>
        {msg && (
          <p className={`text-sm ${msg.type === "ok" ? "text-success" : "text-danger"}`}>
            {msg.text}
          </p>
        )}
        <button
          type="submit"
          disabled={loading}
          className="gradient-btn text-white font-semibold px-6 py-2.5 rounded-xl transition-colors disabled:opacity-50"
        >
          {loading ? "Saving…" : "Save username"}
        </button>
      </form>
    </div>
  );
}

function DeleteAccountCard() {
  const router = useRouter();
  const [step, setStep] = useState<"idle" | "confirm" | "loading">("idle");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleDelete(e: React.FormEvent) {
    e.preventDefault();
    setStep("loading");
    setError("");
    try {
      await deleteAccount(password);
      clearToken();
      router.push("/?deleted=1");
    } catch {
      setError("Incorrect password, or something went wrong. Try again.");
      setStep("confirm");
    }
  }

  return (
    <div className="bg-card border border-danger/30 rounded-2xl p-6 space-y-4">
      <div>
        <h2 className="text-danger font-semibold text-lg">Delete Account</h2>
        <p className="text-text-muted text-sm mt-0.5">
          Permanently deletes your account and all your analyses. This cannot be undone.
        </p>
      </div>

      {step === "idle" && (
        <button
          onClick={() => setStep("confirm")}
          className="border border-danger/40 text-danger font-semibold px-6 py-2.5 rounded-xl hover:bg-danger/10 transition-colors"
        >
          Delete my account
        </button>
      )}

      {(step === "confirm" || step === "loading") && (
        <form onSubmit={handleDelete} className="space-y-3">
          <p className="text-text-muted text-sm">
            Enter your password to confirm. All your data will be deleted immediately.
          </p>
          <PasswordInput
            placeholder="Your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoFocus
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-danger"
          />
          {error && <p className="text-danger text-sm">{error}</p>}
          <div className="flex gap-3">
            <button
              type="submit"
              disabled={step === "loading"}
              className="border border-danger/40 text-danger font-semibold px-6 py-2.5 rounded-xl hover:bg-danger/10 transition-colors disabled:opacity-50"
            >
              {step === "loading" ? "Deleting…" : "Yes, delete everything"}
            </button>
            <button
              type="button"
              onClick={() => { setStep("idle"); setPassword(""); setError(""); }}
              className="text-text-muted text-sm hover:text-text-primary transition-colors px-4"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
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
    if (newPassword.length < 8) {
      setMsg({ type: "err", text: "New password must be at least 8 characters." });
      return;
    }
    setLoading(true);
    setMsg(null);
    try {
      const res = await changePassword(currentPassword, newPassword);
      // The server rotated the session epoch (logging out other devices) and
      // returned a fresh token for THIS device — swap it in so we stay signed in.
      if (res.access_token) setToken(res.access_token);
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
        <PasswordInput
          placeholder="Current password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          required
          autoComplete="current-password"
        />
        <PasswordInput
          placeholder="New password (8+ chars)"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
          autoComplete="new-password"
        />
        <Link href="/forgot-password" className="block text-accent text-sm hover:underline">
          Forgot your current password?
        </Link>
        {msg && (
          <p className={`text-sm ${msg.type === "ok" ? "text-success" : "text-danger"}`}>
            {msg.text}
          </p>
        )}
        <button
          type="submit"
          disabled={loading}
          className="gradient-btn text-white font-semibold px-6 py-2.5 rounded-xl transition-colors disabled:opacity-50"
        >
          {loading ? "Saving…" : "Save password"}
        </button>
      </form>
    </div>
  );
}
