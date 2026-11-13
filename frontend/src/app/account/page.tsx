import type { Metadata } from "next";
import { SiteFrame } from "@/components/site/SiteChrome";
import { AccountPage } from "@/components/site/AccountPage";

export const metadata: Metadata = { title: "Account", robots: { index: false, follow: false } };

export default function Page() {
  return (
    <SiteFrame>
      <AccountPage />
    </SiteFrame>
  );
}
