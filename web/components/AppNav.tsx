"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const AREAS = [
  { href: "/", label: "분석" },
  { href: "/inspect", label: "검사" },
  { href: "/traces", label: "추적" },
  { href: "/stages", label: "스테이지" },
];

type Theme = "dark" | "light";

/**
 * The shell. Theme lives on the document element so CSS switches everything at
 * once, and is stored so a reload does not flip back.
 */
export default function AppNav() {
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
    <header className="nav">
      <span className="nav-brand">
        SSAT <small>정적 분석</small>
      </span>
      {AREAS.map((area) => {
        const active = area.href === "/" ? pathname === "/" : pathname.startsWith(area.href);
        return (
          <Link key={area.href} href={area.href} className={`nav-link ${active ? "is-active" : ""}`}>
            {area.label}
          </Link>
        );
      })}
      <span className="nav-spacer" />
      <button
        type="button"
        className="btn btn-ghost btn-icon"
        onClick={toggle}
        title={theme === "dark" ? "밝은 테마로" : "어두운 테마로"}
        aria-label="테마 전환"
      >
        {theme === "dark" ? "◐" : "◑"}
      </button>
    </header>
  );
}
