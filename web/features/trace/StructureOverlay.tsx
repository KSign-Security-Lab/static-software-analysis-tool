"use client";

import { Maximize2, Repeat, X } from "lucide-react";
import { useEffect, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import GraphPane from "@/features/trace/GraphPane";
import NodeBrief from "@/features/trace/NodeBrief";
import RunLog from "@/features/trace/RunLog";
import { useStructureOpen } from "@/lib/run/selection";

/**
 * 에이전트 구조, at the size the drawing needs.
 *
 * The graph spent its life as the top of the right-hand column, where it was
 * 460x334 with 90px of that spent on a header and a legend. React Flow fitted a
 * sixteen-node pipeline into what was left and landed on scale(0.3): the nodes
 * rendered 37x19, smaller than their own text, so none of the five states they
 * carry could be seen and neither could the one feature that makes this app's
 * tracing worth having -- the chain that produced a finding, marked on the
 * pipeline that produced it.
 *
 * No pane on a four-pane workbench is big enough for that drawing, which is why
 * this is an overlay.
 *
 * ## Deliberately made of nothing
 *
 * Two divs and `createPortal`. It was a Radix `Dialog` and then it was two
 * nested `ResizablePanelGroup`s inside a Radix `Dialog`, and across three
 * attempts the reported symptom was the same: the drawing is not there. The last
 * report was the giveaway -- a tooltip belonging to *this header* floating loose
 * in a corner while the panel itself was nowhere. That is not a layout bug. That
 * is a component whose DOM exists and does not paint, and every candidate for
 * why lived inside machinery this screen does not need: a portal with presence
 * animations, a focus trap, `aria-hidden` juggling on every sibling, and
 * `pointer-events: none` applied to the body.
 *
 * So none of it is here. A backdrop, a panel, an Escape handler, and a portal
 * call that is one line and does exactly what it says. The portal stays because
 * `position: fixed` is measured against the nearest ancestor with a transform
 * rather than the viewport, and this is rendered from inside the workbench --
 * `document.body` is the one parent that cannot surprise it.
 *
 * What is given up: focus is not trapped, so tabbing can walk out of the panel
 * into the page behind. Worth fixing, and worth less than the drawing appearing.
 *
 * ## Why a grid and not resizable panels
 *
 * React Flow measures its container on mount and refuses to draw without one
 * (error #004). A grid track is definite the moment the container is;
 * `minmax(0, 1fr)` on every flexible track is what keeps that true, since a bare
 * `1fr` has an automatic minimum of min-content and one long line of prose in
 * the rail would push the canvas out of the window.
 *
 * The cost is that the regions no longer drag. The split that mattered was the
 * canvas against everything else, and the canvas gets three quarters of the
 * window by construction.
 *
 * ## A reader, not a control surface
 *
 * It carried 검사 실행 and a phase label and a coverage meter, which is a second
 * copy of the navigator's footer and header. Two buttons for one action is fine;
 * two actions wearing one label is a bug waiting for the two to disagree about
 * whether a run is in flight. This draws the pipeline and says nothing about
 * starting one.
 *
 * Open state is in the URL, so a canvas showing one finding's trail is a link.
 */

/**
 * Never changes, so `useSyncExternalStore` never re-subscribes.
 *
 * Module scope on purpose: a new function per render makes the store re-subscribe
 * on every one of them.
 */
const subscribe = () => () => {};

export default function StructureOverlay() {
  const [open, setOpen] = useStructureOpen();
  // Across, now that the rail is gone. Collapsed, the graph is eight ranks by
  // two: a long shallow pipeline in a canvas that is the full width of the
  // window. Top to bottom was right when the canvas was 460 wide and it is not
  // any more. The toggle stays for anyone who disagrees.
  const [direction, setDirection] = useState<"LR" | "TB">("LR");
  const [fit, setFit] = useState(0);

  const close = () => void setOpen(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") void setOpen(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  // Nothing until the client has hydrated.
  //
  // `document` does not exist on the server and the portal needs it, but a bare
  // `typeof document` guard is not enough and saying so was wrong: opening with
  // `?graph=true` already in the address bar makes `open` true on the server
  // too, so the server returned `null` and the client's first pass returned a
  // portal -- and React compares the *shape* of what a component returns, not
  // where a portal ends up putting it. That is a hydration mismatch, and it
  // regenerates this whole tree on the client.
  //
  // `useSyncExternalStore` is the plain way to ask "am I on the client yet":
  // `false` on the server and on the hydrating pass, `true` from the commit
  // after. So both sides agree on `null`, and the overlay arrives one frame
  // later -- which nobody can see, because it only opens from a click or a
  // link that has just been followed.
  const hydrated = useSyncExternalStore(subscribe, () => true, () => false);
  if (!open || !hydrated) return null;

  return createPortal(
    <>
      <div className="fixed inset-0 z-[60] bg-black/60" onClick={close} aria-hidden />

      <div
        role="dialog"
        aria-modal="true"
        aria-label="에이전트 구조"
        // The foot takes more than it did. Collapsed and laid out across, the
        // drawing is about 170px tall however much canvas it is given, so a
        // canvas of 620 was 450 of empty grid -- while the run log showed nine
        // lines of ninety-three and the node panel had no room for a prompt.
        // Space where it is read.
        className="fixed inset-7 z-[61] grid grid-rows-[auto_minmax(0,1fr)_minmax(0,40%)] overflow-hidden rounded-xl border border-line bg-surface shadow-pop"
      >
        <header className="flex h-10 items-center gap-3 border-b border-line px-3">
          <h2 className="shrink-0 text-sm font-semibold text-ink-strong">에이전트 구조</h2>

          {/* Labelled, not icon-and-tooltip. The tooltips these had were the last
              thing still floating out of a portal, and two words are cheaper than
              a floating layer that has to be hovered to be understood. */}
          <span className="flex shrink-0 items-center gap-0.5 rounded-md bg-surface-2 p-0.5">
            <Button
              size="xs"
              variant="ghost"
              className="text-ink-muted"
              onClick={() => setDirection((current) => (current === "TB" ? "LR" : "TB"))}
            >
              <Repeat />
              {direction === "TB" ? "가로로" : "세로로"}
            </Button>
            <Button
              size="xs"
              variant="ghost"
              className="text-ink-muted"
              // A counter, because `fitView` lives on a hook that only works
              // inside the provider `StepGraph` owns -- nothing out here can hold
              // the handle. See `fit` on StepGraph.
              onClick={() => setFit((current) => current + 1)}
            >
              <Maximize2 />
              맞춤
            </Button>
          </span>

          <span className="ml-auto flex shrink-0 items-center gap-1">
            <Button size="icon-xs" variant="ghost" aria-label="닫기" onClick={close}>
              <X className="text-ink-muted" />
            </Button>
          </span>
        </header>

        {/*
          The canvas, full width.

          It had a 320px rail beside it holding the node's card above and a node
          roster otherwise -- which split one subject across two panels, since
          the node's *prompt* was already in the foot. The card and the prompt are
          one panel now, and the roster went with the tangle it was compensating
          for: a searchable list of sixteen nodes is what you need when the
          drawing is too dense to pick from.
        */}
        <div className="min-h-0 min-w-0 border-b border-line">
          <GraphPane direction={direction} fit={fit} />
        </div>

        <div className="grid min-h-0 grid-cols-[minmax(0,45%)_minmax(0,1fr)]">
          <div className="min-h-0 min-w-0 border-r border-line">
            <NodeBrief />
          </div>
          <div className="min-h-0 min-w-0">
            <RunLog />
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
