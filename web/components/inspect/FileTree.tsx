"use client";

import type { SeverityName } from "@/lib/agent-schema";
import { severityLabel, totalCount, worstSeverity } from "@/lib/markers";

/**
 * File list with per-file finding counts.
 *
 * Flat rather than nested: an uploaded tree is usually shallow, and a flat list
 * sorted by severity puts the files that matter at a glance. The badge shows
 * the worst severity in the file, so scanning the list answers "where should I
 * look first" without opening anything.
 */

export interface FileTreeProps {
  files: string[];
  selected: string | null;
  counts: Map<string, Record<SeverityName, number>>;
  onSelect: (path: string) => void;
}

export function FileTree({ files, selected, counts, onSelect }: FileTreeProps) {
  const ordered = [...files].sort((a, b) => {
    const total = totalCount(counts.get(b)) - totalCount(counts.get(a));
    return total !== 0 ? total : a.localeCompare(b);
  });

  return (
    <nav className="filetree" aria-label="파일 목록">
      {ordered.map((path) => {
        const bucket = counts.get(path);
        const worst = worstSeverity(bucket);
        const total = totalCount(bucket);
        return (
          <button
            key={path}
            type="button"
            className={`filetree-row${path === selected ? " is-selected" : ""}`}
            onClick={() => onSelect(path)}
            title={path}
          >
            <span className="filetree-name">{path}</span>
            {total > 0 && worst && (
              <span
                className={`filetree-badge sev-${worst}`}
                title={`${severityLabel(worst)} 포함 ${total}건`}
              >
                {total}
              </span>
            )}
          </button>
        );
      })}
      {ordered.length === 0 && <p className="empty">업로드된 파일이 없습니다.</p>}
    </nav>
  );
}
