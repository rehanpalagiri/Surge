import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import RegisterSW from "@/components/RegisterSW";
import InstallBanner from "@/components/InstallBanner";
import LinkPromptModal from "@/components/LinkPromptModal";
import { Analytics } from "@vercel/analytics/next";

const inter = Inter({ subsets: ["latin"] });

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://surge-chi-khaki.vercel.app";

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
  themeColor: "#7c3aed",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        className={`${inter.className} antialiased bg-background text-text-primary min-h-screen`}
      >
        <RegisterSW />
        {children}
        <LinkPromptModal />
        <InstallBanner />
        <Analytics />
      </body>
    </html>
  );
}
