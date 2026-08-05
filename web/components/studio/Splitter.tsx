"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * A drag handle between two stacked panes.
 *
 * Keyboard as well as pointer, because a divider that can only be moved by
 * dragging is a divider some people cannot move at all. Arrow keys nudge it,
 * Home and End take it to the limits.
 */
export default function Splitter({
  value,
  onChange,
  min,
  max,
  label,
}: {
  /** Share of the container the pane above should take, 0-1. */
  value: number;
  onChange: (share: number) => void;
  min: number;
  max: number;
  label: string;
}) {
  const bar = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const move = useCallback(
    (clientY: number) => {
      const box = bar.current?.parentElement?.getBoundingClientRect();
      if (!box || box.height === 0) return;
      onChange((clientY - box.top) / box.height);
    },
    [onChange],
  );

  useEffect(() => {
    const onMove = (event: PointerEvent) => dragging.current && move(event.clientY);
    const onUp = () => {
      dragging.current = false;
      document.body.classList.remove("is-resizing");
    };
    // On the window, not the handle: the pointer routinely leaves a 6px strip
    // mid-drag, and a listener on the handle would drop the gesture there.
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [move]);

  return (
    <div
      ref={bar}
      className="tx-split"
      role="separator"
      aria-label={label}
      aria-orientation="horizontal"
      aria-valuenow={Math.round(value * 100)}
      aria-valuemin={Math.round(min * 100)}
      aria-valuemax={Math.round(max * 100)}
      tabIndex={0}
      onPointerDown={() => {
        dragging.current = true;
        // Stops the drag selecting text in both panes as it passes over them.
        document.body.classList.add("is-resizing");
      }}
      onKeyDown={(event) => {
        const step = event.shiftKey ? 0.1 : 0.02;
        if (event.key === "ArrowUp") onChange(value - step);
        else if (event.key === "ArrowDown") onChange(value + step);
        else if (event.key === "Home") onChange(min);
        else if (event.key === "End") onChange(max);
        else return;
        event.preventDefault();
      }}
    >
      <span className="tx-split-grip" />
    </div>
  );
}
