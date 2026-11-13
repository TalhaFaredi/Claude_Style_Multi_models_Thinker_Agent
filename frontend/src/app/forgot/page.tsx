import type { Metadata } from "next";
import { SiteFrame } from "@/components/site/SiteChrome";
import { ForgotForm } from "@/components/site/AuthForms";

export const metadata: Metadata = { title: "Reset your password", robots: { index: false, follow: false } };

export default function Page() {
  return (
    <SiteFrame>
      <ForgotForm />
    </SiteFrame>
  );
}
