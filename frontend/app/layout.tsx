import type { Metadata, Viewport } from "next";
import { Instrument_Sans, Schibsted_Grotesk } from "next/font/google";
import "./globals.css";
import RegisterSW from "@/components/RegisterSW";
import InstallBanner from "@/components/InstallBanner";
import LinkPromptModal from "@/components/LinkPromptModal";
import { Analytics } from "@vercel/analytics/next";

const instrumentSans = Instrument_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
});

// Display face for headings and brand moments (--font-display in globals.css).
const schibstedGrotesk = Schibsted_Grotesk({
  subsets: ["latin"],
  style: ["normal", "italic"],
  variable: "--font-schibsted",
});

import { SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: "CraftLint — AI Retention Craft Review",
  description:
    "Find attention risks in your TikTok or Instagram Reel before you post it.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "CraftLint",
  },
  icons: {
    icon: [{ url: "/icon.png", sizes: "192x192", type: "image/png" }],
    apple: [{ url: "/icon-192.png", sizes: "192x192", type: "image/png" }],
  },
  openGraph: {
    title: "CraftLint — Find retention risks before you post",
    description:
      "Review observable retention craft before posting, then track verified results at comparable post ages.",
    url: SITE_URL,
    siteName: "CraftLint",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "CraftLint — Find retention risks before you post",
    description:
      "Review observable retention craft before posting, then track verified results at comparable post ages.",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0A0A0B",
};

// Applies the persisted theme before first paint so a light-theme user never
// sees a dark flash (and vice versa). Dark is the brand default.
const themeInitScript = `try{var t=localStorage.getItem("surge-theme");document.documentElement.setAttribute("data-theme",t==="light"?"light":"dark")}catch(e){document.documentElement.setAttribute("data-theme","dark")}`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className={`${instrumentSans.variable} ${schibstedGrotesk.variable} font-sans antialiased bg-background text-text-primary min-h-screen`}>
        <RegisterSW />
        {children}
        <LinkPromptModal />
        <InstallBanner />
        <Analytics />
      </body>
    </html>
  );
}
