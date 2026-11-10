"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { Icon } from "./Icon";

interface Props {
  title: string;
  /** Omit for dialogs that must finish (e.g. "Summarizing safely"). */
  onClose?: () => void;
  maxWidth?: number;
  footer?: ReactNode;
  children: ReactNode;
}

const FOCUSABLE = 'button:not([disabled]), input, textarea, [href], [tabindex]:not([tabindex="-1"])';

/** Accessible dialog: named, Escape closes, focus moves in and returns, Tab stays inside. */
export function Modal({ title, onClose, maxWidth = 640, footer, children }: Props) {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    return () => previous?.focus?.();
  }, []);

  // Listen on the document, not the dialog: when the focused button unmounts (a dialog that
  // swaps views) focus falls back to <body> and a dialog-level handler would never see the key.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const dialog = ref.current;
      if (!dialog) return;
      if (e.key === "Escape" && closeRef.current) { e.preventDefault(); closeRef.current(); return; }
      if (e.key !== "Tab") return;
      const items = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
      const active = document.activeElement;
      if (items.length === 0 || !dialog.contains(active)) { e.preventDefault(); (items[0] ?? dialog).focus(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="overlay">
      <div ref={ref} className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} style={{ maxWidth }}>
        <div className="modal-head">
          <h2 className="modal-title" id={titleId}>{title}</h2>
          {onClose && (
            <button type="button" className="iconbtn" aria-label="Close" onClick={onClose}>
              <Icon name="close" size={18} />
            </button>
          )}
        </div>
        {children}
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

/** Scrollable body of a dialog. */
export function ModalBody({ children }: { children: ReactNode }) {
  return <div className="modal-body">{children}</div>;
}
