"use client";

import { useEffect, useState } from "react";

import type { Checkpoint } from "@/lib/api/studio";

/**
 * One super-step of the thread.
 *
 * Shows what the node wrote rather than the whole state carried past it -- most
 * of which it never touched. The pencil turns the write into an editable
 * document; `Fork` runs on from it as a new branch, `Re-run from here` takes the
 * same road again unchanged.
 */

export type Granularity = 0 | 1 | 2;
export type Format = "pretty" | "json";

const PREVIEW_CHARS = 120;

function line(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (text === undefined) return "undefined";
  return text.length > PREVIEW_CHARS ? `${text.slice(0, PREVIEW_CHARS)}…` : text;
}

export default function StepCard({
  step,
  changed,
  lane,
  selected,
  granularity,
  format,
  busy,
  interrupted,
  onSelect,
  onFork,
  onRerun,
  loadFull,
}: {
  step: Checkpoint;
  changed: string[];
  lane: number;
  selected: boolean;
  granularity: Granularity;
  format: Format;
  busy: boolean;
  interrupted: boolean;
  onSelect: () => void;
  onFork: (values: Record<string, unknown>) => void;
  onRerun: () => void;
  /** This step's real values. The list the history carries may be a count. */
  loadFull: (checkpointId: string) => Promise<Record<string, unknown>>;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Only what this step wrote is editable. Handing back the whole state would
  // write fields the node never touched, as if it had.
  const written = Object.fromEntries(changed.map((key) => [key, step.values?.[key]]));

  useEffect(() => {
    setEditing(false);
    setError(null);
  }, [step.checkpoint_id]);

  /**
   * Open the editor on the values as they really are.
   *
   * The history summarises the bulky fields -- `pending` arrives as a count and
   * a preview. Editing that and forking would write the summary into the state
   * in place of the list, so the editor loads the step in full first.
   */
  const edit = async () => {
    if (editing) {
      setEditing(false);
      return;
    }
    onSelect();
    setError(null);
    try {
      const full = await loadFull(step.checkpoint_id ?? "");
      setDraft(JSON.stringify(Object.fromEntries(changed.map((key) => [key, full[key]])), null, 2));
      setEditing(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const fork = () => {
    try {
      const parsed: unknown = JSON.parse(draft);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        setError("상태는 객체여야 합니다.");
        return;
      }
      setError(null);
      onFork(parsed as Record<string, unknown>);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const expanded = open || granularity === 2 || editing;
  const stopping = step.next.length > 0 && interrupted && selected;

  return (
    <article
      className={`sx-step ${selected ? "is-selected" : ""} ${lane > 0 ? "is-branch" : ""}`}
      style={lane > 0 ? { marginLeft: Math.min(lane, 4) * 10 } : undefined}
    >
      <header className="sx-step-head">
        <button
          type="button"
          className="sx-step-title"
          onClick={() => {
            onSelect();
            setOpen((v) => !v);
          }}
        >
          <span className="sx-step-caret">{expanded ? "▾" : "▸"}</span>
          <span className="sx-step-node">{step.node ?? step.source ?? "__start__"}</span>
          <span className="sx-step-n">{step.step ?? "—"}</span>
        </button>

        {stopping && <span className="sx-step-paused">paused</span>}

        <button
          type="button"
          className="sx-step-edit"
          title="Edit node state"
          disabled={changed.length === 0}
          onClick={() => void edit()}
        >
          ✎
        </button>
      </header>

      {error && !editing && <p className="sx-error">{error}</p>}

      {granularity >= 1 && !expanded && changed.length > 0 && (
        <p className="sx-step-keys">{changed.join(", ")}</p>
      )}

      {expanded && !editing && (
        <div className="sx-step-body">
          {changed.length === 0 ? (
            <p className="sx-muted">이 단계는 아무것도 쓰지 않았습니다.</p>
          ) : format === "json" ? (
            <pre className="sx-json">{JSON.stringify(written, null, 2)}</pre>
          ) : (
            <dl className="sx-kv">
              {changed.map((key) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{granularity === 2 ? JSON.stringify(step.values?.[key], null, 2) : line(step.values?.[key])}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}

      {editing && (
        <div className="sx-step-body">
          <textarea
            className={`sx-raw ${error ? "is-invalid" : ""}`}
            value={draft}
            spellCheck={false}
            onChange={(event) => setDraft(event.target.value)}
          />
          {error && <p className="sx-error">{error}</p>}
          <div className="sx-step-actions">
            <button type="button" className="sx-submit" disabled={busy} onClick={fork}>
              Fork
            </button>
            <button type="button" className="sx-ghost" disabled={busy} onClick={onRerun}>
              Re-run from here
            </button>
            <button type="button" className="sx-ghost" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
          <p className="sx-muted">
            Fork는 덮어쓰지 않습니다. 이 단계를 부모로 하는 새 갈래가 생기고, 원래 흐름은 그대로 남습니다.
          </p>
        </div>
      )}
    </article>
  );
}
