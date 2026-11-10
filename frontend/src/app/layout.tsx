import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "@/styles/tokens.css";
import "@/styles/base.css";
import "@/styles/layout.css";
import "@/styles/chat.css";
import "@/styles/dialogs.css";

const inter = localFont({ src: "./fonts/inter-latin.woff2", variable: "--font-inter", display: "swap", weight: "100 900", fallback: ["Arial", "sans-serif"] });
const serif = localFont({ src: "./fonts/source-serif-4-latin.woff2", variable: "--font-serif-4", display: "swap", weight: "200 900", fallback: ["Georgia", "serif"] });

export const metadata: Metadata = {
  title: "Multi-Mode Assistant",
  description: "One chat for Simple, Thinker and Planner modes, with live steps, costs and memory in sight.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${serif.variable}`}>
      <body>{children}</body>
    </html>
  );
}
