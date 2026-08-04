"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/**
 * A section's own header: what it is, and its own views.
 *
 * Sub-navigation belongs to the section rather than to a global bar, so
 * "traces" cannot look like a peer of "the agent" when it is part of it.
 */

export interface SectionView {
  href: string;
  label: string;
}

export default function SectionHeader({
  title,
  note,
  views = [],
  children,
}: {
  title: string;
  note?: string;
  views?: SectionView[];
  children?: ReactNode;
}) {
  const pathname = usePathname();

  return (
    <header className="section-head">
      <div className="section-id">
        <h1>{title}</h1>
        {note && <span className="section-note">{note}</span>}
      </div>

      {views.length > 1 && (
        <div className="section-views">
          {views.map((view) => (
            <Link
              key={view.href}
              href={view.href}
              className={`section-view ${pathname === view.href ? "is-active" : ""}`}
            >
              {view.label}
            </Link>
          ))}
        </div>
      )}

      {children && <div className="section-actions">{children}</div>}
    </header>
  );
}
