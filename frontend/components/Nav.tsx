"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { getToken, clearToken } from "@/lib/auth";

export default function Nav({ subtitle }: { subtitle?: string }) {
  const [loggedIn, setLoggedIn] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const pathname = usePathname();

  // Close menu on route change
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

  // Close when clicking outside the menu
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

  function logout() {
    clearToken();
    setMenuOpen(false);
    router.push("/");
  }

  return (
    <nav className="border-b border-border bg-surface/50 backdrop-blur-sm sticky top-0 z-20">
      <div className="max-w-5xl mx-auto px-4 py-4 flex justify-between items-center">

        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="flex items-baseline gap-1.5">
            <Link href="/" className="font-bold text-xl gradient-text">
              Surge
            </Link>
            <span className="text-[10px] text-text-muted/40 font-mono select-none">v1.19</span>
          </div>
          {subtitle && (
            <span className="text-text-muted text-sm capitalize">{subtitle}</span>
          )}
        </div>

        {/* ── Desktop nav (md+) ── */}
        <div className="hidden md:flex items-center gap-4 text-sm">
          {loggedIn ? (
            <>
              <Link href="/projects" className="text-text-muted hover:text-text-primary transition-colors">My Projects</Link>
              <Link href="/profile"  className="text-text-muted hover:text-text-primary transition-colors">Profile</Link>
              <Link href="/settings" className="text-text-muted hover:text-text-primary transition-colors">Settings</Link>
              <button onClick={logout} className="text-text-muted hover:text-danger transition-colors">Log out</button>
            </>
          ) : (
            <>
              <Link href="/login"  className="text-text-muted hover:text-text-primary transition-colors">Log in</Link>
              <Link href="/signup" className="gradient-btn text-white font-semibold px-4 py-1.5 rounded-lg">Sign up</Link>
            </>
          )}
        </div>

        {/* ── Mobile hamburger (< md) ── */}
        <div className="md:hidden relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((o) => !o)}
            aria-label="Toggle menu"
            className="flex flex-col justify-center items-center gap-[5px] w-9 h-9 rounded-lg hover:bg-card transition-colors"
          >
            <span className={`block w-5 h-0.5 bg-text-primary transition-all duration-200 ${menuOpen ? "rotate-45 translate-y-[7px]" : ""}`} />
            <span className={`block w-5 h-0.5 bg-text-primary transition-all duration-200 ${menuOpen ? "opacity-0" : ""}`} />
            <span className={`block w-5 h-0.5 bg-text-primary transition-all duration-200 ${menuOpen ? "-rotate-45 -translate-y-[7px]" : ""}`} />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-12 w-52 bg-card border border-border rounded-2xl shadow-2xl py-2 flex flex-col text-sm z-50">
              {loggedIn ? (
                <>
                  <Link href="/projects" className="px-4 py-3 text-text-muted hover:text-text-primary hover:bg-surface/60 transition-colors">📁 My Projects</Link>
                  <Link href="/profile"  className="px-4 py-3 text-text-muted hover:text-text-primary hover:bg-surface/60 transition-colors">👤 Profile</Link>
                  <Link href="/settings" className="px-4 py-3 text-text-muted hover:text-text-primary hover:bg-surface/60 transition-colors">⚙️ Settings</Link>
                  <div className="border-t border-border my-1" />
                  <button onClick={logout} className="px-4 py-3 text-left text-danger hover:bg-surface/60 transition-colors">Log out</button>
                </>
              ) : (
                <>
                  <Link href="/login"  className="px-4 py-3 text-text-muted hover:text-text-primary hover:bg-surface/60 transition-colors">Log in</Link>
                  <Link href="/signup" className="px-4 py-3 text-text-primary font-semibold hover:bg-surface/60 transition-colors">Sign up free</Link>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
