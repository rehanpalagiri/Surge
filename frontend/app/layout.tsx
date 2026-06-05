import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Surge — AI Video Performance Predictor",
  description: "Find out if your TikTok or Instagram Reel will go viral before you post it.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${inter.className} antialiased bg-background text-text-primary min-h-screen`}
      >
        {children}
      </body>
    </html>
  );
}
