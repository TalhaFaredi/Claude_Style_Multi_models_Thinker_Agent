import type { Metadata } from "next";
import { SiteFrame } from "@/components/site/SiteChrome";
import { SignupForm } from "@/components/site/AuthForms";

export const metadata: Metadata = { title: "Create your account", robots: { index: false, follow: false } };

export default function Page() {
  return (
    <SiteFrame>
      <SignupForm />
    </SiteFrame>
  );
}
