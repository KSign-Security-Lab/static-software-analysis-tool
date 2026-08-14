"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { NO_BREAKPOINTS, type Breakpoints } from "@/lib/api/control";
import { useWriteFile } from "@/lib/run/queries";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * What the run needs that no single pane owns.
 *
 * Two things, and both are here because the 검사 실행 button is not in the pane
 * that knows them: breakpoints are ticked on the graph, inside an overlay, and
 * unsaved text lives in the editor. Beside `stream.tsx` for the same reason it
 * is here -- one per tab, above the routes, so moving between perspectives does
 * not reset them.
 *
 * The drafts half replaces `EditorPane`'s own `useState`, which was keyed on
 * `${runId}:${path}` and reset whenever either changed. Two consequences, both
 * bad and both real: editing `main.c`, opening a finding and coming back lost
 * the text, and 검사 실행 could only ever save the file you happened to be
 * looking at -- so a scan reported on code you had already changed elsewhere.
 *
 * Keyed by path here, which is the whole repair: nothing that changes -- the
 * open file, the open finding, the overlay -- addresses this map, so nothing
 * that changes can empty it.
 */

/** One file's unsaved text, and the server text it was started from. */
export interface Draft {
  text: string;
  /**
   * What the file held when editing began.
   *
   * Kept beside the text rather than compared against the query cache, so
   * "dirty" is answerable without a cache read and cannot flicker when a
   * refetch lands. It is also what makes typing something back to its original
   * value correctly read as clean.
   */
  base: string;
}

interface Controls {
  breakpoints: Breakpoints;
  /** Toggle one node, before it runs or after. */
  toggleBreakpoint: (name: string, when: "before" | "after") => void;
  clearBreakpoints: () => void;

  /** The unsaved text for a path, if there is any. */
  draftOf: (path: string) => string | undefined;
  /** Record what is in the editor. `base` is the server's copy it was started from. */
  setDraft: (path: string, text: string, base: string) => void;
  /** Every path whose draft differs from the server, worst-case in path order. */
  dirty: string[];
  /** Write one path, or every dirty one. Resolves when the server has them. */
  save: (path: string) => Promise<void>;
  saveAll: () => Promise<void>;
  saving: boolean;

  // "Why is the 과정 surface open" lived here and is a URL param now
  // (`useOpenedByRun` in selection.ts): it changes what is on screen, so it must
  // not hide where no link can reproduce it.
}

export type Drafts = ReadonlyMap<string, Draft>;

/**
 * Record what the editor holds for one path.
 *
 * Pure, and separate from the provider, because this is where the rules are:
 * text back at `base` is not a draft, and a path is never keyed by anything but
 * itself. Testing it through a React tree would need a query client, a router
 * and a Monaco mock to assert two lines of set arithmetic.
 */
export function applyDraft(current: Drafts, path: string, text: string, base: string): Drafts {
  const next = new Map(current);
  // Typed back to what the server has is not a draft. Without this, editing and
  // then undoing left the file permanently "dirty", and 검사 실행 went on
  // writing a file whose content it had already written.
  if (text === base) next.delete(path);
  else next.set(path, { text, base });
  return next;
}

/** Every path whose text differs from the server's, in path order. */
export function dirtyOf(drafts: Drafts): string[] {
  return [...drafts.entries()]
    .filter(([, draft]) => draft.text !== draft.base)
    .map(([path]) => path)
    .sort();
}

const ControlsContext = createContext<Controls | null>(null);

export function RunControlsProvider({ children }: { children: ReactNode }) {
  const [runId] = useRunId();
  const write = useWriteFile(runId);

  const [breakpoints, setBreakpoints] = useState<Breakpoints>(NO_BREAKPOINTS);
  const [drafts, setDrafts] = useState<Map<string, Draft>>(() => new Map());

  // Read inside `save`/`saveAll` rather than closed over, so a save writes what
  // is in the editor when the button is pressed rather than what was there when
  // the callback was last built.
  //
  // Mirrored in an effect, not during render: a ref write during render is not
  // safe under a re-render React discards. Both callers run from a click, long
  // after the commit that set this, so there is no staleness to have.
  const latest = useRef(drafts);
  useEffect(() => {
    latest.current = drafts;
  }, [drafts]);

  // A different run's files are not this run's. Adjusted during render rather
  // than in an effect, the way EditorPane's reset was: React re-runs this
  // immediately, so nothing can save one run's text into another.
  const [heldFor, setHeldFor] = useState(runId);
  if (heldFor !== runId) {
    setHeldFor(runId);
    if (drafts.size > 0) setDrafts(new Map());
  }

  const setDraft = useCallback((path: string, text: string, base: string) => {
    setDrafts((current) => applyDraft(current, path, text, base) as Map<string, Draft>);
  }, []);

  const dirty = useMemo(() => dirtyOf(drafts), [drafts]);

  const save = useCallback(
    async (path: string) => {
      const draft = latest.current.get(path);
      if (!runId || !draft || draft.text === draft.base) return;
      await write.mutateAsync({ path, content: draft.text });
      setDrafts((current) => {
        const next = new Map(current);
        next.delete(path);
        return next;
      });
    },
    [runId, write],
  );

  const saveAll = useCallback(async () => {
    // In order and one at a time. These are writes to somebody's source tree
    // and the server answers each with the whole file list; firing them
    // together would have the last response overwrite the tree the others built.
    for (const path of [...latest.current.keys()].sort()) await save(path);
  }, [save]);

  const value = useMemo<Controls>(
    () => ({
      breakpoints,
      toggleBreakpoint: (name, when) =>
        setBreakpoints((current) => {
          const list = current[when];
          return { ...current, [when]: list.includes(name) ? list.filter((n) => n !== name) : [...list, name] };
        }),
      clearBreakpoints: () => setBreakpoints(NO_BREAKPOINTS),
      draftOf: (path) => drafts.get(path)?.text,
      setDraft,
      dirty,
      save,
      saveAll,
      saving: write.isPending,
    }),
    [breakpoints, drafts, setDraft, dirty, save, saveAll, write.isPending],
  );

  return <ControlsContext.Provider value={value}>{children}</ControlsContext.Provider>;
}

export function useRunControls(): Controls {
  const found = useContext(ControlsContext);
  if (!found) throw new Error("useRunControls outside RunControlsProvider");
  return found;
}

/** How many breakpoints are set, for a button that says so without listing them. */
export function countOf(breakpoints: Breakpoints): number {
  return breakpoints.before.length + breakpoints.after.length;
}
