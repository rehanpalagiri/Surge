"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken, clearToken } from "@/lib/auth";

export default function Nav({ subtitle }: { subtitle?: string }) {
  const [loggedIn, setLoggedIn] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const update = () => setLoggedIn(!!getToken());
    update();
    window.addEventListener("viraliq-auth", update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener("viraliq-auth", update);
      window.removeEventListener("storage", update);
    };
  }, []);

  function logout() {
    clearToken();
    router.push("/");
  }

  return (
    <nav className="border-b border-border bg-surface/50 backdrop-blur-sm sticky top-0 z-20">
      <div className="max-w-5xl mx-auto px-4 py-4 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <Link href="/" className="font-bold text-xl gradient-text">
            ViralIQ
          </Link>
          {subtitle && (
            <span className="text-text-muted text-sm capitalize">{subtitle}</span>
          )}
        </div>
        <div className="flex items-center gap-4 text-sm">
          {loggedIn ? (
            <>
              <Link
                href="/projects"
                className="text-text-muted hover:text-text-primary transition-colors"
              >
                My Projects
              </Link>
              <button
                onClick={logout}
                className="text-text-muted hover:text-danger transition-colors"
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="text-text-muted hover:text-text-primary transition-colors"
              >
                Log in
              </Link>
              <Link
                href="/signup"
                className="gradient-btn text-white font-semibold px-4 py-1.5 rounded-lg"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
