"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { money } from "@/domain/format";
import { clearLocalState, isLive } from "@/services/api";
import { auth, type Account } from "@/services/auth";

function useAccount() {
  const [me, setMe] = useState<Account | null | undefined>(undefined);
  useEffect(() => {
    if (!isLive) { setMe(null); return; }
    auth.me().then((a) => {
      if (a === null) window.location.assign("/login?next=/account");
      setMe(a);
    }).catch(() => setMe(null));
  }, []);
  return me;
}

function Message({ kind, children }: { kind: "ok" | "error"; children: React.ReactNode }) {
  return <div className={kind === "ok" ? "alert ok" : "alert"} role={kind === "ok" ? "status" : "alert"}>{children}</div>;
}

function PasswordPanel() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await auth.changePassword(current, next);
      setCurrent("");
      setNext("");
      setMsg({ kind: "ok", text: "Password changed. Your other devices were signed out." });
    } catch (err) {
      setMsg({ kind: "error", text: err instanceof Error ? err.message : "Could not change the password." });
    }
    setBusy(false);
  };
  return (
    <form className="panel form" onSubmit={submit}>
      <h2>Change password</h2>
      {msg && <Message kind={msg.kind}>{msg.text}</Message>}
      <label className="field"><span className="field-label">Current password</span>
        <input className="input" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required /></label>
      <label className="field"><span className="field-label">New password</span>
        <input className="input" type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={10} required />
        <span className="hint">At least 10 characters.</span></label>
      <button className="btn" type="submit" disabled={busy}>{busy ? "Saving..." : "Change password"}</button>
    </form>
  );
}

function DeletePanel() {
  const [password, setPassword] = useState("");
  const [sure, setSure] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await auth.deleteAccount(password);
      clearLocalState();
      window.location.assign("/?deleted=1");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete the account.");
      setBusy(false);
    }
  };
  return (
    <form className="panel danger form" onSubmit={submit}>
      <h2>Delete my account</h2>
      <p style={{ margin: 0 }}>This permanently deletes your account, every chat, uploaded file, generated file and saved memory. It cannot be undone. Download any chat you want to keep first (Settings, then Data, inside the app).</p>
      {error && <Message kind="error">{error}</Message>}
      <label className="field"><span className="field-label">Confirm with your password</span>
        <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
      <label className="check"><input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} /><span>I understand that everything will be deleted.</span></label>
      <button className="btn dark" type="submit" disabled={busy || !sure || !password}>{busy ? "Deleting..." : "Delete everything"}</button>
    </form>
  );
}

export function AccountPage() {
  const me = useAccount();
  const [signingOut, setSigningOut] = useState(false);
  const signOut = async () => {
    setSigningOut(true);
    try { await auth.logout(); } catch { /* the cookie is cleared by the server; leave either way */ }
    clearLocalState();
    window.location.assign("/login");
  };
  if (!isLive) return <><h1 className="page-title">Account</h1><p>Accounts are not used in the offline demo.</p></>;
  if (!me) return <p style={{ marginTop: 40 }} role="status">Loading...</p>;
  const used = me.monthCapUsd > 0 ? Math.min(100, (me.monthSpentUsd / me.monthCapUsd) * 100) : 100;
  return (
    <>
      <h1 className="page-title">Account</h1>
      <p className="page-lead">Signed in as <strong>{me.email}</strong>{me.isAdmin ? " (administrator)" : ""}.</p>
      <div className="row" style={{ marginBottom: 18 }}>
        <Link className="btn primary" href="/app">Open the app</Link>
        {me.isAdmin && <Link className="btn" href="/admin">Admin</Link>}
        <button type="button" className="btn" onClick={signOut} disabled={signingOut}>{signingOut ? "Signing out..." : "Sign out"}</button>
      </div>
      <section className="panel" aria-label="Monthly allowance">
        <h2>Monthly allowance</h2>
        <span>{money(me.monthSpentUsd)} used of {money(me.monthCapUsd)} this month. It renews on the 1st.</span>
        <div className={used >= 80 ? "meter-line hot" : "meter-line"} role="progressbar" aria-valuenow={Math.round(used)} aria-valuemin={0} aria-valuemax={100} aria-label="Allowance used"><div style={{ width: `${used}%` }} /></div>
      </section>
      <PasswordPanel />
      <DeletePanel />
    </>
  );
}
