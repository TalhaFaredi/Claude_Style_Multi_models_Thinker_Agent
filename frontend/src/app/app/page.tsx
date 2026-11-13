import type { Metadata } from "next";
import { AppShell } from "@/components/layout/AppShell";

export const metadata: Metadata = { title: "Assistant", robots: { index: false, follow: false } };

export default function Page() {
  return <AppShell />;
}
