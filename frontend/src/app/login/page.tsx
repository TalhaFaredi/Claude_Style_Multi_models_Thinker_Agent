import type { Metadata } from "next";
import { SiteFrame } from "@/components/site/SiteChrome";
import { LoginForm } from "@/components/site/AuthForms";

export const metadata: Metadata = { title: "Sign in", robots: { index: false, follow: false } };

export default function Page() {
  return (
    <SiteFrame>
      <LoginForm />
    </SiteFrame>
  );
}
