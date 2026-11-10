"use client";

import { useState } from "react";
import type { AiMessage } from "@/domain/messages";
import { useChatStore } from "@/store/chatStore";

/** A risky tool waits on an explicit, per-action decision. */
export function PermissionCard({ message }: { message: AiMessage }) {
  const answer = useChatStore((s) => s.answerPermission);
  const [busy, setBusy] = useState(false);
  const permission = message.permission;
  if (!permission) return null;
  const decide = async (allow: boolean) => {
    setBusy(true);
    try { await answer(message.id, allow); } finally { setBusy(false); }
  };
  return <div className="card warn" role="alert">
    <span className="strong">Allow {permission.tool}?</span>
    <span>{permission.description}</span>
    {permission.arguments != null && <details><summary>Action details</summary><pre className="code-block">{JSON.stringify(permission.arguments, null, 2)}</pre></details>}
    {message.controlError && <span>{message.controlError}. Your decision has not been sent.</span>}
    <div className="row"><button type="button" className="btn" disabled={busy} onClick={() => void decide(false)}>Deny</button><button type="button" className="btn primary" disabled={busy} onClick={() => void decide(true)}>{busy ? "Sending decision..." : "Allow this action"}</button></div>
  </div>;
}
