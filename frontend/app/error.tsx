"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center px-4 text-center">
      <Link href="/" className="font-extrabold text-xl text-text-primary tracking-tight mb-12 font-display">
        Surge
      </Link>

      <h1 className="mt-4 text-2xl sm:text-3xl font-extrabold text-text-primary tracking-tight">
        Something went wrong
      </h1>
      <p className="mt-3 text-text-muted max-w-sm">
        An unexpected error occurred. You can try again or head back home.
      </p>

      <div className="mt-8 flex items-center gap-4">
        <button
          onClick={() => reset()}
          className="gradient-btn text-white font-semibold px-6 py-3 rounded-2xl"
        >
          Try again
        </button>
        <Link
          href="/"
          className="text-text-muted hover:text-text-primary font-semibold px-6 py-3 rounded-2xl transition-colors"
        >
          Back to home
        </Link>
      </div>
    </div>
  );
}
