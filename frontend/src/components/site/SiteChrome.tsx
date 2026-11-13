"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SITE } from "@/domain/site";
import { isLive } from "@/services/api";
import { auth, type Account } from "@/services/auth";
import { Icon } from "../ui/Icon";

function Brand() {
  return (
    <Link href="/" className="site-brand">
      <span className="mark"><Icon name="logo" size={14} stroke="#fff" width={2.4} /></span>
      {SITE.name}
    </Link>
  );
}

/** Sign-in buttons, or "Open the app" once signed in. Rendered after mount, so the static page never depends on a session. */
export function HeaderActions() {
  const [me, setMe] = useState<Account | null | undefined>(undefined);
  useEffect(() => {
    if (!isLive) { setMe(null); return; }
    let live = true;
    auth.me().then((a) => live && setMe(a)).catch(() => live && setMe(null));
    return () => { live = false; };
  }, []);
  if (me === undefined) return <nav className="site-nav" aria-label="Account" />;
  return (
    <nav className="site-nav" aria-label="Account">
      {me ? (
        <>
          {me.isAdmin && <Link className="btn ghost small" href="/admin">Admin</Link>}
          <Link className="btn ghost small" href="/account">Account</Link>
          <Link className="btn primary small" href="/app">Open the app</Link>
        </>
      ) : isLive ? (
        <>
          <Link className="btn ghost small" href="/login">Sign in</Link>
          <Link className="btn primary small" href="/signup">Create account</Link>
        </>
      ) : (
        <Link className="btn primary small" href="/app">Try the demo</Link>
      )}
    </nav>
  );
}

export function SiteHeader() {
  return (
    <header className="site-header">
      <Brand />
      <HeaderActions />
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <span>&copy; {new Date().getFullYear()} {SITE.operator || SITE.name}</span>
      <nav aria-label="Legal">
        <Link href="/terms">Terms</Link>
        <Link href="/privacy">Privacy</Link>
        {SITE.contact && <a href={`mailto:${SITE.contact}`}>Contact</a>}
      </nav>
    </footer>
  );
}

/** Page frame for every public page. */
export function SiteFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="site">
      <SiteHeader />
      <main className="site-main">{children}</main>
      <SiteFooter />
    </div>
  );
}
