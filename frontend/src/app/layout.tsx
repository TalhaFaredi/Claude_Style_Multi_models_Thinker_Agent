import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "@/styles/tokens.css";
import "@/styles/base.css";
import "@/styles/layout.css";
import "@/styles/chat.css";
import "@/styles/dialogs.css";
import "@/styles/site.css";
import { SITE } from "@/domain/site";

const inter = localFont({ src: "./fonts/inter-latin.woff2", variable: "--font-inter", display: "swap", weight: "100 900", fallback: ["Arial", "sans-serif"] });
const serif = localFont({ src: "./fonts/source-serif-4-latin.woff2", variable: "--font-serif-4", display: "swap", weight: "200 900", fallback: ["Georgia", "serif"] });

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  title: { default: `${SITE.name}: one assistant, three ways to think`, template: `%s | ${SITE.name}` },
  description: "One chat for Simple, Thinker and Planner modes, with live steps, costs and memory in sight.",
  applicationName: SITE.name,
  openGraph: { type: "website", siteName: SITE.name, title: SITE.name, description: "Ask quickly, debate with a team of agents, or plan and build a finished document, with the cost in plain sight." },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${serif.variable}`}>
      <body>{children}</body>
    </html>
  );
}
