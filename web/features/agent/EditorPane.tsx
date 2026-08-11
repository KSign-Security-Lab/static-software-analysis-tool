"use client";

import { FileCode, FilePlus, FolderUp, Play, Save } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import CodeEditor from "@/components/editor/CodeEditor.lazy";
import { Button } from "@/components/ui/button";
import { PanelShell } from "@/components/workbench/PanelShell";
import { fromAgent, type UiFinding } from "@/lib/model/finding";
import { useFile, useFindings, useStartRun, useWriteFile } from "@/lib/run/queries";
import { STARTER, useCreateFile, useUploadTree } from "@/lib/run/new-file";
import { useRunStream } from "@/lib/run/stream";
import { cn } from "@/lib/utils";
import { useCentreView, useOpenFile, useRevealLine, useSelectedFinding } from "@/lib/run/selection";

/**
 * The centre pane: one file, its markers, and the two buttons that act on it.
 *
 * Draft text is local state, not the query cache. The cache holds what the
 * server has; typing has not been sent anywhere yet, and writing every
 * keystroke into it would make "dirty" impossible to see.
 */
export default function EditorPane({ runId }: { runId: string | null }) {
  const [path] = useOpenFile();
  const [line] = useRevealLine();
  const [selectedId, setSelectedId] = useSelectedFinding();
  const { ensureAttached, phase } = useRunStream();
  const [, setCentre] = useCentreView();

  const file = useFile(runId, path);
  const findings = useFindings(runId);
  const write = useWriteFile(runId);
  const newFile = useCreateFile();
  const upload = useUploadTree();
  const start = useStartRun(runId, ensureAttached);

  const [draft, setDraft] = useState<string | null>(null);

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

  // A new file means a new draft: keeping the old one would show one file's
  // text under another's name. Adjusted during render rather than in an
  // effect -- React re-runs this component immediately, before the browser
  // sees anything, instead of painting the stale text and then correcting it.
  const [openedAs, setOpenedAs] = useState<string | null>(`${runId}:${path}`);
  const identity = `${runId}:${path}`;
  if (openedAs !== identity) {
    setOpenedAs(identity);
    setDraft(null);
  }

  const server = file.data?.content ?? "";
  const value = draft ?? server;
  const dirty = draft !== null && draft !== server;

  const ui = useMemo<UiFinding[]>(() => fromAgent(findings.data?.findings ?? []), [findings.data]);
  const selected = useMemo(() => ui.find((each) => each.id === selectedId) ?? null, [ui, selectedId]);

  const running = phase === "running" || phase === "starting";
  const canSave = Boolean(runId && path && dirty && !write.isPending);

  const save = () => {
    if (!runId || !path || !dirty) return;
    write.mutate({ path, content: value });
  };

  /**
   * Start the run, then show it running.
   *
   * An inspection takes minutes and the code has nothing to say for the first
   * of them: 문제 fills in only as chunks finish, so pressing the button and
   * watching the editor looks like pressing it did nothing. The graph is where
   * a run is legible while it happens.
   *
   * A tab, not a navigation -- this used to push /agent/trace, which meant
   * leaving the page, and getting back cost a rail click and your open file.
   * On success rather than on click, so a start that is refused leaves the
   * centre where it was.
   */
  const inspect = () => {
    if (!runId) return;
    const watch = { onSuccess: () => void setCentre("graph") };
    // Save first: inspecting text that is only in the editor would report on
    // code the server has never seen.
    if (dirty && path) write.mutate({ path, content: value }, { onSuccess: () => start.mutate({}, watch) });
    else start.mutate({}, watch);
  };

  return (
    <div className="relative h-full min-h-0" {...dropping}>
    <PanelShell
      title={path ?? "편집기"}
      note={dirty ? "저장되지 않음" : undefined}
      actions={
        <>
          <Button variant="ghost" size="xs" onClick={save} disabled={!canSave}>
            <Save />
            {write.isPending ? "저장 중…" : dirty ? "저장" : "저장됨"}
          </Button>
          <Button size="xs" onClick={inspect} disabled={!runId || running}>
            <Play />
            {running ? "검사 중…" : "검사 실행"}
          </Button>
        </>
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
          onChange={setDraft}
          onSave={save}
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
