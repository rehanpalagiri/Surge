"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { getToken, clearToken } from "@/lib/auth";
import { Skeleton } from "@/components/Skeleton";

export default function Nav({ subtitle }: { subtitle?: string }) {
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
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

  function logout() {
    clearToken();
    setMenuOpen(false);
    router.push("/");
  }

  return (
    <nav className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm sticky top-0 z-20">
      <div className="max-w-5xl mx-auto px-4 py-4 flex justify-between items-center">

        {/* Logo */}
        <div className="flex items-center gap-3">
          <Link href="/" className="font-bold text-xl text-purple-500 tracking-tight">
            Surge
          </Link>
          {subtitle && (
            <span className="text-zinc-500 text-sm capitalize">{subtitle}</span>
          )}
        </div>

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
              <Link href="/" className="text-zinc-400 hover:text-white transition-colors">Dashboard</Link>
              <Link href="/projects" className="text-zinc-400 hover:text-white transition-colors">Experiments</Link>
              <Link href="/profile"  className="text-zinc-400 hover:text-white transition-colors">Profile</Link>
              <Link href="/settings" className="text-zinc-400 hover:text-white transition-colors">Settings</Link>
              <button onClick={logout} className="text-zinc-400 hover:text-white transition-colors">Log out</button>
            </>
          ) : (
            <>
              <Link href="/login"  className="text-zinc-400 hover:text-white transition-colors">Log in</Link>
              <Link href="/signup" className="bg-purple-600 hover:bg-purple-500 text-white font-semibold px-4 py-1.5 rounded-lg transition-colors">Sign up</Link>
            </>
          )}
        </div>

        {/* ── Mobile hamburger (< md) ── */}
        <div className="md:hidden relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((o) => !o)}
            disabled={loggedIn === null}
            aria-label="Toggle menu"
            className="flex flex-col justify-center items-center gap-[5px] w-9 h-9 rounded-lg hover:bg-zinc-800 transition-colors"
          >
            <span className={`block w-5 h-0.5 bg-white transition-all duration-200 ${menuOpen ? "rotate-45 translate-y-[7px]" : ""}`} />
            <span className={`block w-5 h-0.5 bg-white transition-all duration-200 ${menuOpen ? "opacity-0" : ""}`} />
            <span className={`block w-5 h-0.5 bg-white transition-all duration-200 ${menuOpen ? "-rotate-45 -translate-y-[7px]" : ""}`} />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-12 w-52 bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl py-2 flex flex-col text-sm z-50">
              {loggedIn ? (
                <>
                  <Link href="/" className="px-4 py-3 text-zinc-400 hover:text-white hover:bg-zinc-800/60 transition-colors">Dashboard</Link>
                  <Link href="/projects" className="px-4 py-3 text-zinc-400 hover:text-white hover:bg-zinc-800/60 transition-colors">Experiments</Link>
                  <Link href="/profile"  className="px-4 py-3 text-zinc-400 hover:text-white hover:bg-zinc-800/60 transition-colors">Profile</Link>
                  <Link href="/settings" className="px-4 py-3 text-zinc-400 hover:text-white hover:bg-zinc-800/60 transition-colors">Settings</Link>
                  <div className="border-t border-zinc-700 my-1" />
                  <button onClick={logout} className="px-4 py-3 text-left text-zinc-400 hover:text-white hover:bg-zinc-800/60 transition-colors">Log out</button>
                </>
              ) : (
                <>
                  <Link href="/login"  className="px-4 py-3 text-zinc-400 hover:text-white hover:bg-zinc-800/60 transition-colors">Log in</Link>
                  <Link href="/signup" className="px-4 py-3 text-white font-semibold hover:bg-zinc-800/60 transition-colors">Sign up free</Link>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
