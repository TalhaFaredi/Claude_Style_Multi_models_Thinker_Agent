import type { Metadata } from "next";
import { SiteFrame } from "@/components/site/SiteChrome";
import { AdminPage } from "@/components/site/AdminPage";

export const metadata: Metadata = { title: "Admin", robots: { index: false, follow: false } };

export default function Page() {
  return (
    <SiteFrame>
      <AdminPage />
    </SiteFrame>
  );
}
