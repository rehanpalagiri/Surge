"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import Nav from "@/components/Nav";
import { getToken } from "@/lib/auth";
import { SettingsSkeleton } from "@/components/Skeleton";

const TABS: { href: string; label: string; danger?: boolean }[] = [
  { href: "/settings/account", label: "Account" },
  { href: "/settings/plan", label: "Plan" },
  { href: "/settings/privacy", label: "Privacy" },
  { href: "/settings/danger", label: "Danger zone", danger: true },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace(`/login?next=${encodeURIComponent(pathname || "/settings/account")}`);
      return;
    }
    setAuthReady(true);
  }, [router, pathname]);

  return (
    <main className="min-h-screen flex flex-col bg-background">
      <Nav subtitle="Settings" />
      <div className="max-w-4xl mx-auto w-full px-4 py-10">
        {!authReady ? (
          <SettingsSkeleton />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-[180px_1fr] gap-8">
            <nav aria-label="Settings sections" className="flex md:flex-col gap-1 overflow-x-auto md:overflow-visible pb-2 md:pb-0">
              {TABS.map((tab) => {
                const active = pathname === tab.href;
                return (
                  <Link
                    key={tab.href}
                    href={tab.href}
                    className={`shrink-0 rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors ${
                      active
                        ? tab.danger
                          ? "bg-danger/10 text-danger"
                          : "bg-accent/10 text-accent"
                        : tab.danger
                        ? "text-danger/70 hover:bg-danger/5 hover:text-danger"
                        : "text-text-muted hover:bg-surface hover:text-text-primary"
                    }`}
                  >
                    {tab.label}
                  </Link>
                );
              })}
            </nav>

            <div className="space-y-4 min-w-0">
              {children}
              <p className="text-center text-text-muted/60 text-xs pt-6">
                <Link href="/privacy" className="hover:text-text-muted transition-colors">Privacy Policy</Link>
                <span className="mx-2">·</span>
                <Link href="/terms" className="hover:text-text-muted transition-colors">Terms of Service</Link>
              </p>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
