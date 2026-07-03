// Canonical site URL — the ONLY place the production origin is defined.
// Set NEXT_PUBLIC_SITE_URL (Vercel env) when the custom domain goes live;
// every consumer (metadata, OG image, robots, sitemap, Terms of Service)
// follows automatically.
export const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://surge-chi-khaki.vercel.app";

/** Display host, e.g. "surge-chi-khaki.vercel.app" — for prose like the ToS. */
export const SITE_HOST = new URL(SITE_URL).host;
