"use client";

import { FileCode, FilePlus, FolderUp, Save } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import CodeEditor from "@/components/editor/CodeEditor.lazy";
import { Button } from "@/components/ui/button";
import { PanelShell } from "@/components/workbench/PanelShell";
import { fromAgent, type UiFinding } from "@/lib/model/finding";
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
  const [path] = useOpenFile();
  const [line] = useRevealLine();
  const [, setSelectedId] = useSelectedFinding();
  const { draftOf, setDraft, save, saving } = useRunControls();

  const file = useFile(runId, path);
  const findings = useFindings(runId);
  const newFile = useCreateFile();
  const upload = useUploadTree();

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
  const selected = useOpenFinding(runId) ?? null;

  const canSave = Boolean(runId && path && dirty && !saving);

  return (
    <div className="relative h-full min-h-0" {...dropping}>
    <PanelShell
      title={path ?? "편집기"}
      note={dirty ? "저장되지 않음" : undefined}
      actions={
        <Button
          variant="ghost"
          size="xs"
          onClick={() => path && void save(path)}
          disabled={!canSave}
        >
          <Save />
          {saving ? "저장 중…" : dirty ? "저장" : "저장됨"}
        </Button>
      }
      bodyClassName={cn("overflow-hidden", !path && "grid place-items-center")}
    >
      {path ? (
        <CodeEditor
          path={path}
          value={value}
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
