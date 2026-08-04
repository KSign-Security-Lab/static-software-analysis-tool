"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Three sections, down the side.
 *
 * They are separate products that happen to share a repo -- an LLM agent, the
 * F2-A evidence pipeline, and graph extraction -- not three views of one thing.
 * A horizontal tab strip said the opposite, and put the agent fourth. A rail
 * makes the split structural and leaves the top bar to whatever the section
 * itself needs.
 */

const SECTIONS = [
  {
    href: "/agent",
    label: "에이전트",
    note: "LLM 검사",
    // Sparkline-ish: reads as "reasoning" rather than a generic robot.
    icon: (
      <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M3 13.5 6.5 8l3 3.5L13 5l4 8.5" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="13" cy="5" r="1.8" fill="currentColor" stroke="none" />
      </svg>
    ),
  },
  {
    href: "/f2a",
    label: "F2-A",
    note: "근거 추적",
    icon: (
      <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M10 2.5 16.5 5v5c0 3.4-2.7 6.2-6.5 7.5C6.2 16.2 3.5 13.4 3.5 10V5z" strokeLinejoin="round" />
        <path d="M7.5 10l1.8 1.8L13 8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    href: "/extract",
    label: "추출",
    note: "CPG · AST · DFG",
    icon: (
      <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6">
        <circle cx="10" cy="4" r="2.2" />
        <circle cx="4.5" cy="15" r="2.2" />
        <circle cx="15.5" cy="15" r="2.2" />
        <path d="M8.6 5.9 5.9 12.9M11.4 5.9l2.7 7M6.7 15h6.6" strokeLinecap="round" />
      </svg>
    ),
  },
];

type Theme = "dark" | "light";

export default function SectionRail() {
  const pathname = usePathname();
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const stored = (localStorage.getItem("ssat-theme") as Theme | null) ?? "dark";
    setTheme(stored);
    document.documentElement.dataset.theme = stored;
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    localStorage.setItem("ssat-theme", next);
  };

  return (
    <nav className="rail" aria-label="섹션">
      <span className="rail-brand" title="Static Software Analysis Tool">
        SS
        <br />
        AT
      </span>

      {SECTIONS.map((section) => (
        <Link
          key={section.href}
          href={section.href}
          className={`rail-item ${pathname.startsWith(section.href) ? "is-active" : ""}`}
          title={`${section.label} — ${section.note}`}
        >
          {section.icon}
          <span className="rail-label">{section.label}</span>
        </Link>
      ))}

      <span className="rail-spacer" />
      <button type="button" className="rail-item rail-toggle" onClick={toggle} aria-label="테마 전환">
        <span aria-hidden>{theme === "dark" ? "◐" : "◑"}</span>
      </button>
    </nav>
  );
}
