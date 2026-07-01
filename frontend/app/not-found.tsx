import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center px-4 text-center">
      <Link href="/" className="font-extrabold text-xl text-purple-500 tracking-tight mb-12">
        Surge
      </Link>

      <p className="text-7xl sm:text-8xl font-extrabold text-white tracking-tight">404</p>
      <h1 className="mt-4 text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
        Page not found
      </h1>
      <p className="mt-3 text-zinc-400 max-w-sm">
        The page you&apos;re looking for doesn&apos;t exist or has moved.
      </p>

      <Link
        href="/"
        className="gradient-btn mt-8 text-white font-semibold px-6 py-3 rounded-2xl"
      >
        Back to home
      </Link>
    </div>
  );
}
