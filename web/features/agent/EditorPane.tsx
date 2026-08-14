"use client";

import { FileCode, FilePlus, FolderUp, Save, TriangleAlert } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import CodeEditor from "@/components/editor/CodeEditor.lazy";
import { Button } from "@/components/ui/button";
import { PanelShell } from "@/components/workbench/PanelShell";
import FileTabs from "@/features/agent/FileTabs";
import { ago } from "@/lib/format";
import { countByFile, fromAgent, type UiFinding } from "@/lib/model/finding";
import { useFile, useFindings, useOpenFinding } from "@/lib/run/queries";
import { STARTER, useCreateFile, useUploadTree } from "@/lib/run/new-file";
import { useRunControls } from "@/lib/run/controls";
import { useRunId } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";
import { useOpenFile, useRevealLine, useSelectedFinding } from "@/lib/run/selection";

/**
 * The centre pane: one file, its markers, and the one button that acts on it.
 *
 * 검사 실행 used to be here as well, and also on the graph, each with its own
 * `useStartRun`. Starting a run is not an operation on the open file -- it
 * inspects every file in the run -- so it is on the run bar with the rest of
 * the run's state, and this is left doing one thing.
 *
 * Unsaved text is not local state either, and that was a bug rather than a
 * decision: it lived in a `useState` reset whenever the run or the path changed,
 * so opening a finding threw the reader's edit away without saying so. It is in
 * `lib/run/controls.tsx` now, keyed by path -- nothing that changes on this
 * screen addresses that map, so nothing that changes can empty it. Still not the
 * query cache, which holds what the server has.
 */
export default function EditorPane() {
  // Read here rather than passed in: the centre slot is a server component now
  // that this is the whole of it, and every other consumer of the run id gets it
  // from the same hook anyway.
  const [runId] = useRunId();
  const [path, setPath] = useOpenFile();
  const [line] = useRevealLine();
  const [, setSelectedId] = useSelectedFinding();
  const { draftOf, setDraft, save, saving, savedAt, dirty: dirtyPaths } = useRunControls();

  const file = useFile(runId, path);
  const findings = useFindings(runId);
  const newFile = useCreateFile();
  const upload = useUploadTree();

  /**
   * The files this reader has open.
   *
   * `useState` here rather than a store: the centre slot mounts once for the
   * surface, so this survives every file switch without one, and a tab list is
   * not worth a URL parameter -- `?file=` already says which one is *active*,
   * which is the part worth linking to.
   *
   * Adjusted during render rather than in an effect, the way the drafts store
   * resets on a run change: React re-runs this immediately, so the strip is never
   * a frame behind the file it is labelling.
   */
  const [open, setOpen] = useState<string[]>([]);
  const [openedFor, setOpenedFor] = useState(runId);
  if (openedFor !== runId) {
    setOpenedFor(runId);
    setOpen(path ? [path] : []);
  } else if (path && !open.includes(path)) {
    setOpen([...open, path]);
  }

  const closeTab = (each: string) => {
    const rest = open.filter((name) => name !== each);
    setOpen(rest);
    // Closing the one you are looking at has to land somewhere. The neighbour to
    // the left is where the eye already is.
    if (each === path) void setPath(rest[Math.max(0, open.indexOf(each) - 1)] ?? null);
  };

  /**
   * Dropping a folder here.
   *
   * Uploading a tree is what anyone with a real codebase is trying to do, and
   * the only way in was an unlabelled folder icon in the explorer's header. The
   * centre is where the eye and the pointer already are.
   *
   * Depth-counted, because dragenter and dragleave fire again for every child
   * the pointer crosses -- a plain boolean flickers off the moment the cursor
   * passes over the text inside the drop zone.
   */
  const [over, setOver] = useState(false);
  const depth = useRef(0);
  const picker = useRef<HTMLInputElement>(null);

  const hasFiles = (event: React.DragEvent) => event.dataTransfer.types.includes("Files");
  const dropping = {
    onDragEnter: (event: React.DragEvent) => {
      if (!hasFiles(event)) return;
      depth.current += 1;
      setOver(true);
    },
    onDragOver: (event: React.DragEvent) => {
      if (!hasFiles(event)) return;
      // Without this the browser leaves the app and opens the file instead.
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
    },
    onDragLeave: () => {
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) setOver(false);
    },
    onDrop: (event: React.DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth.current = 0;
      setOver(false);
      void upload.drop(event.dataTransfer);
    },
  };

  // No reset when the path changes: the store is keyed by path, so the draft
  // for the file being left stays where it is and the one being opened is
  // whatever that file already had. This is where the reset used to be, and
  // where it destroyed the reader's text on every finding they clicked.
  const server = file.data?.content ?? "";
  const draft = path ? draftOf(path) : undefined;
  const value = draft ?? server;
  const dirty = draft !== undefined && draft !== server;

  const ui = useMemo<UiFinding[]>(() => fromAgent(findings.data?.findings ?? []), [findings.data]);
  const counts = useMemo(() => countByFile(ui), [ui]);
  const selected = useOpenFinding(runId) ?? null;

  const canSave = Boolean(runId && path && dirty && !saving);

  /**
   * Whether the report still describes what is in this file.
   *
   * `POST /agent/runs/{id}/apply` splices a fix in by matching the finding's
   * `primary.excerpt` against the file, and **409s** when they no longer agree.
   * Nothing said so until the patch had been pressed and the toast came back, so
   * this says it first -- an unsaved edit to a line the report quotes is exactly
   * the state where 이대로 고치기 is about to fail.
   */
  const stale = useMemo(() => {
    if (!path) return false;
    const quoted = ui.filter((each) => each.primary.file === path && each.primary.excerpt);
    if (quoted.length === 0) return false;
    return quoted.some((each) => !value.includes(each.primary.excerpt!.trim()));
  }, [ui, path, value]);

  return (
    <div className="relative h-full min-h-0" {...dropping}>
    <PanelShell
      // No title once a file is open: the tabs are the identity, and a header
      // repeating the path above them was a second name for the same thing. It
      // was briefly the file's *directory*, which at the root of a run is the
      // empty string -- so the pane called itself 편집기 while showing `util.c`.
      title={path ? undefined : "편집기"}
      bodyClassName={cn("flex flex-col overflow-hidden", !path && "grid place-items-center")}
    >
      {path && (
        <>
          <FileTabs
            open={open}
            active={path}
            dirty={dirtyPaths}
            counts={counts}
            onPick={(each) => void setPath(each)}
            onClose={closeTab}
          />

          {/*
            The file's own state, on its own row.

            저장 was an `xs` ghost in the panel header -- the same mistake 검사
            실행 had, and for the same reason it was fixed: this writes to
            somebody's source tree and it should not look like a toolbar icon.
            The row also has room for the two things nothing was saying: when the
            file was last written, and whether the report still matches it.
          */}
          <div className="flex h-9 shrink-0 items-center gap-3 border-b border-line px-3">
            {/* The path in full, since the tab only has room for the basename --
                and this row was otherwise blank most of the time, which is a
                32px band of nothing above the code. */}
            <span className="min-w-0 truncate font-mono text-2xs text-ink-faint">{path}</span>

            <span className="ml-auto flex shrink-0 items-center gap-3">
              {stale && (
                <span
                  className="flex items-center gap-1.5 rounded-sm bg-warn-wash px-1.5 py-0.5 text-2xs text-warn"
                  title="보고서가 인용한 코드가 지금 파일에 없습니다. ‘이대로 고치기’는 실패합니다."
                >
                  <TriangleAlert className="size-3 shrink-0" />
                  지난 검사 이후 바뀜
                </span>
              )}

              <span className="text-2xs text-ink-faint">
                {saving
                  ? "저장 중…"
                  : dirty
                    ? "저장되지 않음"
                    : savedAt.has(path)
                      ? `${ago(savedAt.get(path)!)}에 저장함`
                      : "저장됨"}
              </span>

              {/* Filled, always. It was a ghost that read `저장됨` -- which is a
                  status wearing a button's clothes, and the same mistake 검사
                  실행 had. Disabled when there is nothing to write, so it is
                  quiet without pretending to be a label. */}
              <Button size="sm" className="shrink-0" onClick={() => path && void save(path)} disabled={!canSave}>
                <Save />
                저장
              </Button>
            </span>
          </div>
        </>
      )}

      {path ? (
        <CodeEditor
          path={path}
          value={value}
          density="comfortable"
          language={file.data?.language}
          findings={ui}
          selected={selected}
          line={line}
          // `server` as the base, so typing back to what the file already holds
          // registers as clean rather than as an edit that never goes away.
          onChange={(text) => setDraft(path, text, server)}
          onSave={() => void save(path)}
          onRevealFinding={(finding) => void setSelectedId(finding.id)}
        />
      ) : (
        /* The first thing anyone sees, so it offers the first move rather than
           describing it. The two buttons run the same commands the explorer's
           icons and ⌘N do -- one registry, so this cannot drift from them. */
        <div className="max-w-96 space-y-4 p-6 text-center">
          <div className="space-y-1.5">
            <p className="text-md font-semibold text-ink-strong">검사할 코드를 넣어 주세요</p>
            <p className="text-sm leading-relaxed text-ink-faint">
              폴더를 여기에 끌어다 놓으면 통째로 검사합니다. 파일 하나만 붙여넣어도 됩니다. 넣은 코드는 이 컴퓨터를
              벗어나지 않습니다.
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            <Button size="sm" disabled={upload.busy} onClick={() => picker.current?.click()}>
              <FolderUp />
              {upload.busy ? "올리는 중…" : "폴더 열기"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={newFile.busy}
              onClick={() => void newFile.create("main.c", STARTER)}
            >
              <FileCode />
              예제로 시작
            </Button>
            <Button size="sm" variant="outline" onClick={() => void newFile.create("new.c")}>
              <FilePlus />빈 파일 만들기
            </Button>
          </div>
          {/* A picker as well as the drop zone: dragging is not available to
              everyone, and a keyboard has nothing to drag with. */}
          <input
            ref={picker}
            type="file"
            multiple
            hidden
            {...{ webkitdirectory: "" }}
            onChange={(event) => {
              const picked = Array.from(event.target.files ?? []);
              upload.send(picked);
              event.target.value = "";
            }}
          />
        </div>
      )}
    </PanelShell>

    {over && (
      <div className="pointer-events-none absolute inset-2 z-10 grid place-items-center rounded-md border-2 border-dashed border-accent bg-bg/85">
        <p className="flex items-center gap-2 text-sm font-medium text-accent-ink">
          <FolderUp className="size-4" />
          놓으면 이 폴더로 새 검사를 시작합니다
        </p>
      </div>
    )}
    </div>
  );
}
