"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * One shell over every area, so the app is navigable rather than a set of
 * pages you have to know the URL of. Before the merge these were separate
 * apps; afterwards two of them had no link at all.
 */

const AREAS = [
  { href: "/", label: "분석", note: "CPG · 파이프라인 · F2-A" },
  { href: "/stages", label: "스테이지", note: "단계별 실행" },
  { href: "/inspect", label: "검사", note: "LLM 에이전트" },
  { href: "/traces", label: "추적", note: "LangSmith" },
];

export default function AppNav() {
  const pathname = usePathname();
  return (
    <header className="appnav">
      <span className="appnav-brand">SSAT</span>
      <nav>
        {AREAS.map((area) => {
          const active = area.href === "/" ? pathname === "/" : pathname.startsWith(area.href);
          return (
            <Link key={area.href} href={area.href} className={`appnav-link ${active ? "is-active" : ""}`}>
              {area.label}
              <span className="appnav-note">{area.note}</span>
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
