"use client";

import type { FileCount, Severity } from "@/lib/model/finding";
import { SEVERITY_LABEL } from "@/lib/model/finding";

/** Files in the target, worst finding first. Shared by both analysis pages. */
export default function FileTree({
  files,
  selected,
  counts,
  onSelect,
}: {
  files: string[];
  selected: string | null;
  counts: Map<string, FileCount>;
  onSelect: (path: string) => void;
}) {
  const ordered = [...files].sort((a, b) => {
    const diff = (counts.get(b)?.total ?? 0) - (counts.get(a)?.total ?? 0);
    return diff !== 0 ? diff : a.localeCompare(b);
  });

  if (ordered.length === 0) {
    return <p className="ws-empty">파일이 없습니다.</p>;
  }

  return (
    <nav className="ws-files" aria-label="파일">
      {ordered.map((path) => {
        const count = counts.get(path);
        return (
          <button
            key={path}
            type="button"
            title={path}
            className={`ws-file ${path === selected ? "is-selected" : ""}`}
            onClick={() => onSelect(path)}
          >
            <span className="ws-file-name">{path}</span>
            {count && count.worst && (
              <span
                className={`ws-badge sev-${count.worst}`}
                title={`${SEVERITY_LABEL[count.worst as Severity]} 포함 ${count.total}건`}
              >
                {count.total}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
