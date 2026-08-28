"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * Lay an editor out when its box changes, on the frame *after* being told.
 *
 * Monaco's own `automaticLayout` observes the container and lays out inside the
 * ResizeObserver callback. Laying out writes to the DOM -- scrollbars, view zones,
 * the overview ruler -- which can change the size of an observed element, so the
 * observer is re-entered during its own delivery. Past the loop limit the browser
 * gives up with "ResizeObserver loop completed with undelivered notifications" and
 * *drops the notifications it has not delivered yet*.
 *
 * Which notification gets dropped is not ours to choose. In this app the editor
 * sits inside a resizable panel group that has an observer of its own, and the
 * panel's `onResize` is how a fold is reported; losing it is how the fold buttons
 * came to disagree with the panels. Chrome tends to deliver everything and log the
 * warning; Safari is stricter about the cycle, which is why this showed up there.
 *
 * A `requestAnimationFrame` moves the layout out of the delivery cycle entirely, so
 * whatever it changes is a fresh observation rather than a re-entry. Coalesced to
 * one frame, because a drag emits an observation per frame and Monaco's layout is
 * not cheap.
 *
 * Returns the observer *and* a way to ask for a layout without one, which the
 * editors need on mount: see `relayout` below.
 */
export function useDeferredLayout(layout: () => void) {
  const frame = useRef<number | null>(null);
  const latest = useRef(layout);

  // In an effect, not during render: a ref written while rendering is a lint error
  // and, more to the point, a render that is thrown away would leave the wrong
  // callback behind. The observer below is attached during commit and its first
  // delivery is after paint, so this has always run by the time it fires.
  useEffect(() => {
    latest.current = layout;
  }, [layout]);

  useEffect(
    () => () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    },
    [],
  );

  /**
   * Lay out on the next frame, unprompted by any resize.
   *
   * The editors need this on mount, and without it they were sometimes 5×5
   * pixels in a 920×491 container -- Monaco's floor when it measures a box that
   * has no size yet.
   *
   * `automaticLayout` is off, so an editor is laid out exactly twice: once by its
   * own constructor, measuring the container as it finds it, and thereafter only
   * when the observer below reports a change. Attaching the observer delivers one
   * guaranteed notification, and that notification arrives *before the editor
   * exists* -- Monaco is loaded asynchronously, which is what the `loading`
   * placeholder is for -- so the one certain layout was spent on a null ref. If
   * the constructor's own measurement then landed in a frame where the flex chain
   * had not resolved, nothing ever corrected it: the container never changes size
   * again by itself, so no second notification is coming. Hence blank until the
   * pane is dragged, which is the first real resize and repairs it.
   */
  const relayout = useCallback(() => {
    if (frame.current !== null) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      latest.current();
    });
  }, []);

  /** Attach to the element wrapping the editor. */
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
