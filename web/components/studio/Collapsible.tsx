"use client";

import { useState, type ReactNode } from "react";

/**
 * A panel that can be folded away.
 *
 * Open by default, and remembered by whoever passes `onToggle` -- the panel
 * being there is the useful state, and hiding a thing people came to read
 * behind a click they have to discover is not a saving.
 *
 * Controlled when given `onToggle`, uncontrolled otherwise; the second form is
 * for panels nobody needs to remember the state of.
 */
export default function Collapsible({
  title,
  note,
  children,
  open: initiallyOpen = true,
  onToggle,
}: {
  title: string;
  note?: string;
  children: ReactNode;
  open?: boolean;
  onToggle?: (open: boolean) => void;
}) {
  const [ownOpen, setOwnOpen] = useState(initiallyOpen);
  const open = onToggle ? initiallyOpen : ownOpen;
  const toggle = () => (onToggle ? onToggle(!open) : setOwnOpen(!open));

  return (
    <section className={`tx-fold ${open ? "is-open" : ""}`}>
      <button type="button" className="tx-fold-head" aria-expanded={open} onClick={toggle}>
        <span className="tx-fold-caret">{open ? "▾" : "▸"}</span>
        <span className="tx-fold-title">{title}</span>
        {note && <span className="tx-fold-note">{note}</span>}
      </button>
      {open && <div className="tx-fold-body">{children}</div>}
    </section>
  );
}
