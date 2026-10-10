import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Noto_Sans_Devanagari, Outfit } from "next/font/google";

import "./globals.css";
import { Providers } from "./providers";

const display = Outfit({ subsets: ["latin"], variable: "--font-display", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });
const deva = Noto_Sans_Devanagari({ subsets: ["devanagari"], variable: "--font-deva", display: "swap" });

export const metadata: Metadata = {
  title: "CoolRoof — heat and rooftop solar",
  description: "Which roofs should a city cool first, and can your home go solar?",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#120d0a" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${mono.variable} ${deva.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
