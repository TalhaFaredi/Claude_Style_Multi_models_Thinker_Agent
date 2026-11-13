import type { Metadata } from "next";
import { SiteFrame } from "@/components/site/SiteChrome";
import { ContactLine, Operator, TemplateNotice } from "@/components/site/Legal";
import { SITE } from "@/domain/site";

export const metadata: Metadata = { title: "Terms of use", alternates: { canonical: "/terms" } };

export default function Terms() {
  return (
    <SiteFrame>
      <article className="legal">
        <h1>Terms of use</h1>
        <p className="hint">Last updated: {new Date().getFullYear()}</p>
        <TemplateNotice />
        <p>These terms govern your use of {SITE.name} (the &ldquo;Service&rdquo;), provided by <Operator />. By creating an account or using the Service you accept them.</p>

        <h2>1. The Service</h2>
        <p>{SITE.name} lets you ask questions of AI language models, optionally with documents, web search and planning tools. Answers come from third-party models. The Service is provided as is and may change, be interrupted or be withdrawn.</p>

        <h2>2. Your account</h2>
        <ul>
          <li>You must give a working e-mail address and keep your password secret. You are responsible for what happens under your account.</li>
          <li>One person per account. Do not share access or create accounts to avoid limits.</li>
          <li>You can delete your account at any time from the Account page. We may suspend or close accounts that break these terms.</li>
        </ul>

        <h2>3. Allowance and limits</h2>
        <p>Each account has a monthly usage allowance, a limit per question, limits on storage and on how many questions can run at once. These limits protect the Service and may change. When an allowance is used up, paid model features stop until it renews.</p>

        <h2>4. Acceptable use</h2>
        <p>Do not use the Service to break the law, to harm or harass others, to create malware, to infringe others&rsquo; rights, to attempt to access other people&rsquo;s data, to probe or overload the Service, or to generate content that the underlying model providers prohibit. Do not upload material you have no right to use.</p>

        <h2>5. AI output</h2>
        <p>AI answers can be wrong, incomplete or out of date, and may resemble existing material. Check anything important before relying on it. Nothing in the Service is legal, medical, financial or other professional advice. You are responsible for how you use the output.</p>

        <h2>6. Your content</h2>
        <p>You keep your rights in what you put in. You give us permission to store, process and send it to the model and tool providers described in the Privacy Policy, only to run the Service for you. We do not use your content to train our own models.</p>

        <h2>7. Availability, liability and changes</h2>
        <p>To the fullest extent the law allows, the Service is provided without warranties, and <Operator /> is not liable for indirect or consequential losses, lost data or lost profits. Nothing here limits liability that cannot be limited by law. Keep your own copies of anything important: you can download any chat from inside the app.</p>
        <p>We may update these terms; the date above shows the latest version. Continuing to use the Service after a change means you accept it.</p>

        <h2>8. Contact</h2>
        <p>Questions about these terms: <ContactLine />.</p>
      </article>
    </SiteFrame>
  );
}
