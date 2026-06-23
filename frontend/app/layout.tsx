import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import RegisterSW from "@/components/RegisterSW";
import InstallBanner from "@/components/InstallBanner";
import ReportIssue from "@/components/ReportIssue";
import LinkPromptModal from "@/components/LinkPromptModal";
import { Analytics } from "@vercel/analytics/next";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Surge — AI Video Performance Predictor",
  description:
    "Find out if your TikTok or Instagram Reel will go viral before you post it.",
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
    title: "Surge — Will your video go viral?",
    description:
      "Upload your TikTok or Instagram Reel and get an AI breakdown in seconds — hook strength, pacing, audio, captions, trend alignment, and a full improvement plan.",
    url: "https://surge-chi-khaki.vercel.app",
    siteName: "Surge",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Surge — Will your video go viral?",
    description:
      "Upload your TikTok or Instagram Reel and get an AI breakdown in seconds — hook strength, pacing, audio, captions, trend alignment, and a full improvement plan.",
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
        <ReportIssue />
        <Analytics />
      </body>
    </html>
  );
}
