import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import RegisterSW from "@/components/RegisterSW";
import InstallBanner from "@/components/InstallBanner";
import LinkPromptModal from "@/components/LinkPromptModal";
import { Analytics } from "@vercel/analytics/next";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  metadataBase: new URL("https://surge-chi-khaki.vercel.app"),
  title: "Surge — AI Video Craft Review",
  description:
    "Get an AI-assisted craft review of your TikTok or Instagram Reel before you post it.",
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
    title: "Surge — Review your video before you post",
    description:
      "Review observable video craft before posting, then track verified results at comparable post ages.",
    url: "https://surge-chi-khaki.vercel.app",
    siteName: "Surge",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Surge — Review your video before you post",
    description:
      "Review observable video craft before posting, then track verified results at comparable post ages.",
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
