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
  title: "Surge — AI Retention Craft Review",
  description:
    "Find attention risks in your TikTok or Instagram Reel before you post it.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Surge",
  },
  icons: {
    icon: [{ url: "/icon.png", sizes: "192x192", type: "image/png" }],
    apple: [{ url: "/icon-192.png", sizes: "192x192", type: "image/png" }],
  },
  openGraph: {
    title: "Surge — Find retention risks before you post",
    description:
      "Review observable retention craft before posting, then track verified results at comparable post ages.",
    url: SITE_URL,
    siteName: "Surge",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Surge — Find retention risks before you post",
    description:
      "Review observable retention craft before posting, then track verified results at comparable post ages.",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#FFFFFF",
};

// Applies the persisted theme before first paint. Light is the first-visit
// default; an explicit saved dark preference is still respected.
const themeInitScript = `try{var t=localStorage.getItem("surge-theme");document.documentElement.setAttribute("data-theme",t==="dark"?"dark":"light")}catch(e){document.documentElement.setAttribute("data-theme","light")}`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
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
