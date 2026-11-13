import type { Metadata } from "next";
import { SiteFrame } from "@/components/site/SiteChrome";
import { ContactLine, Operator, TemplateNotice } from "@/components/site/Legal";
import { SITE } from "@/domain/site";

export const metadata: Metadata = { title: "Privacy policy", alternates: { canonical: "/privacy" } };

export default function Privacy() {
  return (
    <SiteFrame>
      <article className="legal">
        <h1>Privacy policy</h1>
        <p className="hint">Last updated: {new Date().getFullYear()}</p>
        <TemplateNotice />
        <p><Operator /> runs {SITE.name} and is responsible for the personal data described here. Contact: <ContactLine />.</p>

        <h2>What we store</h2>
        <ul>
          <li><strong>Account:</strong> your e-mail address and a salted, one-way hash of your password (we cannot read your password).</li>
          <li><strong>Your content:</strong> your chats (every message), files you upload and the text read from them, files the assistant generates for you, and the memories it keeps about you when long-term memory is on.</li>
          <li><strong>Settings and usage:</strong> your preferences and a spending log (time, model, tokens and cost of each call). The log holds no message text.</li>
          <li><strong>Sessions:</strong> when you sign in we record a session with its time, IP address and browser description, to keep you signed in and to protect the account.</li>
        </ul>

        <h2>Who receives your content</h2>
        <p>To answer you, the Service sends your messages, the relevant parts of your files and, in some modes, web search queries to third parties:</p>
        <ul>
          <li><strong>AI model providers</strong>, reached through OpenRouter (and other configured providers), which pass requests to the companies that run the models. By default the Service asks for providers that do not keep or train on prompts; you can change this in Settings.</li>
          <li><strong>Document reading services</strong>, only when you choose a paid reader for scans or charts: the selected page images are sent for text recognition.</li>
          <li><strong>Web search and web pages</strong>, only when the web tool is on: search queries and the addresses opened are visible to those services.</li>
        </ul>
        <p>We do not sell your data and we do not show advertising. We do not use your content to train our own models.</p>

        <h2>Cookies</h2>
        <p>The Service sets one essential cookie that keeps you signed in. It is not used for tracking or advertising, so no cookie banner is needed. Your browser also stores a few display preferences locally.</p>

        <h2>How long we keep it</h2>
        <ul>
          <li>Chats, files and memories stay until you delete them. Deleting a chat removes its messages, files, search indexes and generated files.</li>
          <li>Deleting your account removes all of the above and your sign-in details. The spending log keeps its numbers without any content.</li>
          <li>Routine backups of the database are kept for a limited period (by default 14 days) and then overwritten, so deleted data can remain in backups until they expire.</li>
        </ul>

        <h2>Your rights</h2>
        <p>You can download any chat (Settings, then Data), view and delete what the assistant remembers about you, change your password and delete your account yourself. Depending on where you live you may also have the right to access, correct, restrict or object to our use of your data or to complain to a data-protection authority. Write to <ContactLine /> to use these rights.</p>

        <h2>Security</h2>
        <p>The Service uses encrypted connections, hashed passwords, per-account separation of data, rate limiting and spending caps. No system is perfectly secure; choose a strong, unique password and avoid putting secrets you cannot afford to share with the model providers into a chat.</p>

        <h2>Children</h2>
        <p>The Service is not meant for people under 16.</p>

        <h2>Changes</h2>
        <p>If this policy changes, the date above changes. Material changes will be announced in the app or by e-mail.</p>
      </article>
    </SiteFrame>
  );
}
