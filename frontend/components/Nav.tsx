"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { getToken } from "@/lib/auth";
import { Skeleton } from "@/components/Skeleton";
import ThemeToggle from "@/components/ThemeToggle";

export default function Nav({ subtitle }: { subtitle?: string }) {
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  useEffect(() => { setMenuOpen(false); }, [pathname]);

  useEffect(() => {
    const update = () => setLoggedIn(!!getToken());
    update();
    window.addEventListener("surge-auth", update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener("surge-auth", update);
      window.removeEventListener("storage", update);
    };
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  return (
    <nav className="border-b border-border bg-background/85 backdrop-blur-sm sticky top-0 z-20">
      <div className="max-w-5xl mx-auto px-4 py-4 flex justify-between items-center">

        {/* Logo */}
        <div className="flex items-center gap-3">
          <Link href="/" className="font-bold text-xl text-text-primary tracking-tight font-display">
            Surge
          </Link>
          {subtitle && (
            <span className="text-text-muted text-sm capitalize">{subtitle}</span>
          )}
        </div>

        <div className="flex items-center gap-3">
        {/* ── Desktop nav (md+) ── */}
        <div className="hidden md:flex items-center gap-5 text-sm">
          {loggedIn === null ? (
            <div className="flex items-center gap-4" aria-label="Checking account session" aria-busy="true">
              <Skeleton className="h-4 w-16 rounded-md" />
              <Skeleton className="h-4 w-20 rounded-md" />
              <Skeleton className="h-8 w-20 rounded-lg" />
            </div>
          ) : loggedIn ? (
            <>
              <Link href="/" className="text-text-muted hover:text-text-primary transition-colors">Dashboard</Link>
              <Link href="/projects" className="text-text-muted hover:text-text-primary transition-colors">Projects</Link>
              <Link href="/insights" className="text-text-muted hover:text-text-primary transition-colors">Insights</Link>
              <Link href="/settings" className="text-text-muted hover:text-text-primary transition-colors">Settings</Link>
            </>
          ) : (
            <>
              <Link href="/login"  className="text-text-muted hover:text-text-primary transition-colors">Log in</Link>
              <Link href="/signup" className="gradient-btn text-white font-semibold px-4 py-1.5 rounded-lg">Sign up</Link>
            </>
          )}
        </div>

        <ThemeToggle />

        {/* ── Mobile hamburger (< md) ── */}
        <div className="md:hidden relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((o) => !o)}
            disabled={loggedIn === null}
            aria-label="Toggle menu"
            className="flex flex-col justify-center items-center gap-[5px] w-9 h-9 rounded-lg hover:bg-surface transition-colors"
          >
            <span className={`block w-5 h-0.5 bg-text-primary transition-all duration-200 ${menuOpen ? "rotate-45 translate-y-[7px]" : ""}`} />
            <span className={`block w-5 h-0.5 bg-text-primary transition-all duration-200 ${menuOpen ? "opacity-0" : ""}`} />
            <span className={`block w-5 h-0.5 bg-text-primary transition-all duration-200 ${menuOpen ? "-rotate-45 -translate-y-[7px]" : ""}`} />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-12 w-52 bg-card border border-border rounded-2xl shadow-xl py-2 flex flex-col text-sm z-50">
              {loggedIn ? (
                <>
                  <Link href="/" className="px-4 py-3 text-text-muted hover:text-text-primary hover:bg-surface transition-colors">Dashboard</Link>
                  <Link href="/projects" className="px-4 py-3 text-text-muted hover:text-text-primary hover:bg-surface transition-colors">Projects</Link>
                  <Link href="/insights" className="px-4 py-3 text-text-muted hover:text-text-primary hover:bg-surface transition-colors">Insights</Link>
                  <Link href="/settings" className="px-4 py-3 text-text-muted hover:text-text-primary hover:bg-surface transition-colors">Settings</Link>
                </>
              ) : (
                <>
                  <Link href="/login"  className="px-4 py-3 text-text-muted hover:text-text-primary hover:bg-surface transition-colors">Log in</Link>
                  <Link href="/signup" className="px-4 py-3 text-text-primary font-semibold hover:bg-surface transition-colors">Sign up free</Link>
                </>
              )}
            </div>
          )}
        </div>
        </div>
      </div>
    </nav>
  );
}
