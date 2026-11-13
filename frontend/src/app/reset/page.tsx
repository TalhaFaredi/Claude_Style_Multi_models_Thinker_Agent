import type { Metadata } from "next";
import { SiteFrame } from "@/components/site/SiteChrome";
import { ResetForm } from "@/components/site/AuthForms";

export const metadata: Metadata = { title: "Choose a new password", robots: { index: false, follow: false } };

export default function Page() {
  return (
    <SiteFrame>
      <ResetForm />
    </SiteFrame>
  );
}
