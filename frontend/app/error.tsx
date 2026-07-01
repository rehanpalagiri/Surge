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
    <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center px-4 text-center">
      <Link href="/" className="font-extrabold text-xl text-purple-500 tracking-tight mb-12">
        Surge
      </Link>

      <h1 className="mt-4 text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
        Something went wrong
      </h1>
      <p className="mt-3 text-zinc-400 max-w-sm">
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
          className="text-zinc-400 hover:text-white font-semibold px-6 py-3 rounded-2xl transition-colors"
        >
          Back to home
        </Link>
      </div>
    </div>
  );
}
