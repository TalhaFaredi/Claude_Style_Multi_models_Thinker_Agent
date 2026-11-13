"use client";

import { useEffect } from "react";

export default function ErrorPage({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => { console.error(error); }, [error]);
  return (
    <main className="boot" role="alert">
      <div className="card" style={{ maxWidth: 520 }}>
        <span className="strong">Something went wrong</span>
        <span>The page hit an unexpected problem. Your chats are safe on the server.</span>
        <div className="row">
          <button type="button" className="btn primary" onClick={() => retry()}>Try again</button>
          <a className="btn" href="/">Home</a>
        </div>
      </div>
    </main>
  );
}
