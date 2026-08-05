"use client";

import { useEffect, useRef, useState } from "react";

import type { Breakpoints } from "@/lib/api/studio";

/**
 * The bar under the input: settings, where to stop, and go.
 *
 * `Interrupt` opens a list of the graph's nodes with a before/after toggle on
 * each, which is the same set the `+` badges on the canvas write to. `Submit`
 * carries a dropdown for the variant nobody wants by default -- throwing away
 * cached chunk results and inspecting the tree again from nothing.
 */

function useDismiss(onDismiss: () => void) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as globalThis.Node)) onDismiss();
    };
    const escape = (event: KeyboardEvent) => event.key === "Escape" && onDismiss();

    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [onDismiss]);

  return box;
}

function InterruptMenu({
  steppable,
  breakpoints,
  onToggle,
  onClear,
  onDismiss,
}: {
  steppable: string[];
  breakpoints: Breakpoints;
  onToggle: (node: string, when: "before" | "after") => void;
  onClear: () => void;
  onDismiss: () => void;
}) {
  const box = useDismiss(onDismiss);
  const before = new Set(breakpoints.before);
  const after = new Set(breakpoints.after);

  return (
    <div className="sx-menu" ref={box}>
      <div className="sx-menu-head">
        <span>Interrupt</span>
        <span className="sx-menu-cols">
          <span>before</span>
          <span>after</span>
        </span>
      </div>

      {steppable.map((node) => (
        <div key={node} className="sx-menu-row">
          <span className="sx-menu-node">{node}</span>
          <span className="sx-menu-cols">
            <input type="checkbox" checked={before.has(node)} onChange={() => onToggle(node, "before")} />
            <input type="checkbox" checked={after.has(node)} onChange={() => onToggle(node, "after")} />
          </span>
        </div>
      ))}

      <button type="button" className="sx-menu-clear" onClick={onClear}>
        모두 해제
      </button>
    </div>
  );
}

export default function RunSettingsBar({
  steppable,
  breakpoints,
  onToggleBreakpoint,
  onClearBreakpoints,
  onSubmit,
  onResume,
  onAbort,
  onOpenSettings,
  running,
  interrupted,
  busy,
  disabled,
}: {
  steppable: string[];
  breakpoints: Breakpoints;
  onToggleBreakpoint: (node: string, when: "before" | "after") => void;
  onClearBreakpoints: () => void;
  onSubmit: (force: boolean) => void;
  onResume: () => void;
  onAbort: () => void;
  onOpenSettings: () => void;
  running: boolean;
  interrupted: boolean;
  busy: boolean;
  disabled: boolean;
}) {
  const [menu, setMenu] = useState<null | "interrupt" | "submit">(null);
  const submitBox = useDismiss(() => setMenu((m) => (m === "submit" ? null : m)));

  const count = breakpoints.before.length + breakpoints.after.length;
  // Locked while the graph is going: interrupts are compiled in, so changing
  // one mid-run would be a lie about where it will stop.
  const locked = running || interrupted;

  return (
    <div className="sx-runbar">
      <button type="button" className="sx-ghost" onClick={onOpenSettings}>
        Settings
      </button>

      <div className="sx-pop">
        <button
          type="button"
          className={`sx-ghost ${count > 0 ? "is-on" : ""}`}
          disabled={locked}
          onClick={() => setMenu((m) => (m === "interrupt" ? null : "interrupt"))}
          title={locked ? "실행 중에는 바꿀 수 없습니다" : "중단점"}
        >
          Interrupt{count > 0 ? ` (${count})` : ""} <span className="sx-caret">▾</span>
        </button>

        {menu === "interrupt" && (
          <InterruptMenu
            steppable={steppable}
            breakpoints={breakpoints}
            onToggle={onToggleBreakpoint}
            onClear={onClearBreakpoints}
            onDismiss={() => setMenu(null)}
          />
        )}
      </div>

      <div className="sx-runbar-spacer" />

      {interrupted ? (
        <>
          <button type="button" className="sx-ghost" disabled={busy} onClick={onAbort}>
            Cancel
          </button>
          <button type="button" className="sx-submit" disabled={busy} onClick={onResume}>
            Continue
          </button>
        </>
      ) : (
        <div className="sx-pop sx-split" ref={submitBox}>
          <button
            type="button"
            className="sx-submit"
            disabled={busy || running || disabled}
            onClick={() => onSubmit(false)}
          >
            {running ? "Running…" : "Submit"}
          </button>
          <button
            type="button"
            className="sx-submit sx-submit-more"
            disabled={busy || running || disabled}
            onClick={() => setMenu((m) => (m === "submit" ? null : "submit"))}
          >
            ▾
          </button>

          {menu === "submit" && (
            <div className="sx-menu sx-menu-right">
              <button
                type="button"
                className="sx-menu-item"
                onClick={() => {
                  setMenu(null);
                  onSubmit(true);
                }}
              >
                Submit &amp; re-inspect everything
                <span className="sx-menu-note">캐시된 청크 결과를 버리고 전부 다시 검사합니다</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
