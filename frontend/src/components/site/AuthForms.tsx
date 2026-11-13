"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { SITE } from "@/domain/site";
import { clearLocalState, isLive, safeNext } from "@/services/api";
import { auth, type AuthConfig } from "@/services/auth";

function useAuthConfig(): AuthConfig | null {
  const [cfg, setCfg] = useState<AuthConfig | null>(null);
  useEffect(() => {
    if (isLive) auth.config().then(setCfg).catch(() => setCfg(null));
  }, []);
  return cfg;
}

const nextParam = () => safeNext(typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("next"));

function DemoNotice() {
  return (
    <div className="alert notice" role="status">
      This copy runs as an offline demo, so there are no accounts. <Link href="/app">Open the demo</Link>.
    </div>
  );
}

function Field(props: { label: string; type?: string; value: string; onChange: (v: string) => void; autoComplete?: string; hint?: string; required?: boolean; minLength?: number }) {
  return (
    <label className="field">
      <span className="field-label">{props.label}</span>
      <input className="input" type={props.type ?? "text"} value={props.value} required={props.required ?? true} minLength={props.minLength}
        autoComplete={props.autoComplete} onChange={(e) => props.onChange(e.target.value)} />
      {props.hint && <span className="hint">{props.hint}</span>}
    </label>
  );
}

function Shell({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h1>{title}</h1>
        {sub && <p className="sub">{sub}</p>}
        {children}
      </div>
    </div>
  );
}

function useSubmit(action: () => Promise<void>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  };
  return { busy, error, submit, setBusy };
}

export function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const cfg = useAuthConfig();
  const { busy, error, submit } = useSubmit(async () => {
    await auth.login(email, password);
    clearLocalState();   // another person may have used this browser before
    window.location.assign(nextParam());
  });
  if (!isLive) return <Shell title="Sign in"><DemoNotice /></Shell>;
  return (
    <Shell title="Sign in" sub={`Welcome back to ${SITE.name}.`}>
      <form className="form" onSubmit={submit}>
        {error && <div className="alert" role="alert">{error}</div>}
        <Field label="E-mail" type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field label="Password" type="password" value={password} onChange={setPassword} autoComplete="current-password" />
        <button className="btn primary" type="submit" disabled={busy}>{busy ? "Signing in..." : "Sign in"}</button>
      </form>
      <div className="auth-links">
        <Link href="/forgot">Forgot your password?</Link>
        {cfg?.signupOpen !== false && <Link href="/signup">Create an account</Link>}
      </div>
    </Shell>
  );
}

export function SignupForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invite, setInvite] = useState("");
  const [agreed, setAgreed] = useState(false);
  const cfg = useAuthConfig();
  const min = cfg?.minPasswordLength ?? 10;
  const { busy, error, submit } = useSubmit(async () => {
    await auth.signup(email, password, invite);
    clearLocalState();
    window.location.assign(nextParam());
  });
  if (!isLive) return <Shell title="Create your account"><DemoNotice /></Shell>;
  if (cfg && !cfg.signupOpen) {
    return (
      <Shell title="Sign-ups are closed">
        <p>New accounts are not being accepted right now.{SITE.contact ? <> Write to <a href={`mailto:${SITE.contact}`}>{SITE.contact}</a> to ask for access.</> : null}</p>
        <div className="auth-links"><Link href="/login">Sign in</Link></div>
      </Shell>
    );
  }
  return (
    <Shell title="Create your account" sub="Your chats and memory stay private to your account.">
      <form className="form" onSubmit={submit}>
        {error && <div className="alert" role="alert">{error}</div>}
        <Field label="E-mail" type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field label="Password" type="password" value={password} onChange={setPassword} autoComplete="new-password" minLength={min} hint={`At least ${min} characters. A few random words make a strong one.`} />
        {cfg?.inviteRequired && <Field label="Invite code" value={invite} onChange={setInvite} autoComplete="off" />}
        <label className="check">
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} required />
          <span>I have read and accept the <Link href="/terms" target="_blank">Terms</Link> and the <Link href="/privacy" target="_blank">Privacy Policy</Link>.</span>
        </label>
        <button className="btn primary" type="submit" disabled={busy || !agreed}>{busy ? "Creating..." : "Create account"}</button>
      </form>
      <div className="auth-links"><span>Already have an account?</span><Link href="/login">Sign in</Link></div>
    </Shell>
  );
}

export function ForgotForm() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState("");
  const cfg = useAuthConfig();
  const { busy, error, submit } = useSubmit(async () => {
    setDone((await auth.forgot(email)).message);
  });
  if (!isLive) return <Shell title="Reset your password"><DemoNotice /></Shell>;
  if (cfg && !cfg.passwordResetByEmail) {
    return (
      <Shell title="Reset your password">
        <p>Password reset by e-mail is not set up on this server.{SITE.contact ? <> Write to <a href={`mailto:${SITE.contact}`}>{SITE.contact}</a> and an administrator will help.</> : " Ask the administrator to reset it."}</p>
        <div className="auth-links"><Link href="/login">Back to sign in</Link></div>
      </Shell>
    );
  }
  return (
    <Shell title="Reset your password" sub="We will e-mail you a link that works for one hour.">
      {done ? (
        <div className="alert ok" role="status">{done}</div>
      ) : (
        <form className="form" onSubmit={submit}>
          {error && <div className="alert" role="alert">{error}</div>}
          <Field label="E-mail" type="email" value={email} onChange={setEmail} autoComplete="email" />
          <button className="btn primary" type="submit" disabled={busy}>{busy ? "Sending..." : "Send reset link"}</button>
        </form>
      )}
      <div className="auth-links"><Link href="/login">Back to sign in</Link></div>
    </Shell>
  );
}

export function ResetForm() {
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const cfg = useAuthConfig();
  const min = cfg?.minPasswordLength ?? 10;
  useEffect(() => { setToken(new URLSearchParams(window.location.search).get("token") ?? ""); }, []);
  const { busy, error, submit } = useSubmit(async () => {
    await auth.reset(token, password);
    clearLocalState();
    window.location.assign("/app");
  });
  if (!isLive) return <Shell title="Choose a new password"><DemoNotice /></Shell>;
  return (
    <Shell title="Choose a new password" sub="You will be signed out on every other device.">
      <form className="form" onSubmit={submit}>
        {!token && <div className="alert" role="alert">This link is incomplete. Open the link from your e-mail again.</div>}
        {error && <div className="alert" role="alert">{error}</div>}
        <Field label="New password" type="password" value={password} onChange={setPassword} autoComplete="new-password" minLength={min} hint={`At least ${min} characters.`} />
        <button className="btn primary" type="submit" disabled={busy || !token}>{busy ? "Saving..." : "Save password"}</button>
      </form>
      <div className="auth-links"><Link href="/forgot">Need a new link?</Link></div>
    </Shell>
  );
}
