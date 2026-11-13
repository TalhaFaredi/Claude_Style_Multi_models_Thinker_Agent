"use client";

import { useCallback, useEffect, useState } from "react";
import { money } from "@/domain/format";
import { ApiError, isLive } from "@/services/api";
import { auth, type AdminStats, type AdminUser } from "@/services/auth";

const day = (t: number | null) => (t ? new Date(t * 1000).toLocaleDateString() : "never");

export function AdminPage() {
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState("");
  const [forbidden, setForbidden] = useState(false);

  const load = useCallback(async () => {
    try {
      const [u, s] = await Promise.all([auth.adminUsers(), auth.adminStats()]);
      setUsers(u);
      setStats(s);
      setError("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setForbidden(true);
      else setError(e instanceof Error ? e.message : "Could not load the users.");
    }
  }, []);
  useEffect(() => { if (isLive) void load(); }, [load]);

  const patch = async (id: number, body: Parameters<typeof auth.adminPatch>[1]) => {
    try {
      await auth.adminPatch(id, body);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The change was not saved.");
    }
  };
  const setCap = (u: AdminUser) => {
    const answer = window.prompt(`Monthly allowance in USD for ${u.email}\n(empty = server default)`, u.monthlyCap === null ? "" : String(u.monthlyCap));
    if (answer === null) return;
    const value = Number(answer);
    if (answer.trim() === "") void patch(u.id, { resetCap: true });
    else if (Number.isFinite(value) && value >= 0) void patch(u.id, { monthlyCap: value });
    else setError("Enter a number such as 5 or 12.50.");
  };

  if (!isLive) return <p style={{ marginTop: 40 }}>The admin page needs a connected backend.</p>;
  if (forbidden) return <><h1 className="page-title">Admin</h1><p>This page is for administrators.</p></>;
  return (
    <>
      <h1 className="page-title">Admin</h1>
      <p className="page-lead">Users, spending and limits. Allowances apply per calendar month.</p>
      {error && <div className="alert" role="alert" style={{ marginBottom: 16 }}>{error}</div>}
      {stats && (
        <div className="stats">
          <div className="stat"><b>{stats.users}</b><span>users</span></div>
          <div className="stat"><b>{stats.chats}</b><span>chats</span></div>
          <div className="stat"><b>{money(stats.monthSpentUsd)}</b><span>spent this month{stats.globalCapUsd > 0 ? ` of ${money(stats.globalCapUsd)} cap` : " (no global cap)"}</span></div>
          <div className="stat"><b>{stats.activeRuns} / {stats.maxConcurrentRuns}</b><span>questions running now</span></div>
        </div>
      )}
      {!users ? <p role="status">Loading...</p> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>E-mail</th><th>Status</th><th>Chats</th><th>Spent / allowance</th><th>Joined</th><th>Last sign-in</th><th>Actions</th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}{u.isAdmin && <> <span className="pill green">admin</span></>}</td>
                  <td>{u.disabled ? <span className="pill warn">disabled</span> : "active"}</td>
                  <td>{u.chats}</td>
                  <td>{money(u.monthSpentUsd)} / {money(u.effectiveCap)}{u.monthlyCap !== null ? " (custom)" : ""}</td>
                  <td>{day(u.created)}</td>
                  <td>{day(u.lastLogin)}</td>
                  <td>
                    <div className="row">
                      <button type="button" className="btn small" onClick={() => setCap(u)}>Allowance</button>
                      <button type="button" className="btn small" onClick={() => void patch(u.id, { disabled: !u.disabled })}>{u.disabled ? "Enable" : "Disable"}</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
