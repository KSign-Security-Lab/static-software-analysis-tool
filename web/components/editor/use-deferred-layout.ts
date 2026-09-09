"use client";

import { useCallback, useEffect, useRef } from "react";

export function useDeferredLayout(layout: () => void) {
  const frame = useRef<number | null>(null);
  const latest = useRef(layout);

  useEffect(() => {
    latest.current = layout;
  }, [layout]);

  useEffect(
    () => () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    },
    [],
  );

  const relayout = useCallback(() => {
    if (frame.current !== null) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      latest.current();
    });
  }, []);

  const observe = useCallback(
    (element: HTMLElement | null) => {
      if (frame.current !== null) {
        cancelAnimationFrame(frame.current);
        frame.current = null;
      }
      if (!element || typeof ResizeObserver === "undefined") return;

      const observer = new ResizeObserver(() => relayout());
      observer.observe(element);
      return () => observer.disconnect();
    },
    [relayout],
  );

  return { observe, relayout };
}
