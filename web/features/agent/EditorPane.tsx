"use client";

import { FileCode, FilePlus, Play, Save } from "lucide-react";
import { useMemo, useState } from "react";

import CodeEditor from "@/components/editor/CodeEditor.lazy";
import { Button } from "@/components/ui/button";
import { PanelShell } from "@/components/workbench/PanelShell";
import { fromAgent, type UiFinding } from "@/lib/model/finding";
import { useFile, useFindings, useStartRun, useWriteFile } from "@/lib/run/queries";
import { STARTER, useCreateFile } from "@/lib/run/new-file";
import { useRunStream } from "@/lib/run/stream";
import { cn } from "@/lib/utils";
import { useCentreView, useOpenFile, useSelectedFinding } from "@/lib/run/selection";

/**
 * The centre pane: one file, its markers, and the two buttons that act on it.
 *
 * Draft text is local state, not the query cache. The cache holds what the
 * server has; typing has not been sent anywhere yet, and writing every
 * keystroke into it would make "dirty" impossible to see.
 */
export default function EditorPane({ runId }: { runId: string | null }) {
  const [path] = useOpenFile();
  const [selectedId, setSelectedId] = useSelectedFinding();
  const { ensureAttached, phase } = useRunStream();
  const [, setCentre] = useCentreView();

  const file = useFile(runId, path);
  const findings = useFindings(runId);
  const write = useWriteFile(runId);
  const newFile = useCreateFile();
  const start = useStartRun(runId, ensureAttached);

  const [draft, setDraft] = useState<string | null>(null);

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
              왼쪽 탐색기에서 파일을 고르거나, 여기서 바로 시작할 수 있습니다. 넣은 코드는 이 컴퓨터를 벗어나지
              않습니다.
            </p>
          </div>
          <div className="flex justify-center gap-2">
            <Button size="sm" disabled={newFile.busy} onClick={() => void newFile.create("main.c", STARTER)}>
              <FileCode />
              예제로 시작
            </Button>
            <Button size="sm" variant="outline" onClick={() => void newFile.create("new.c")}>
              <FilePlus />빈 파일 만들기
            </Button>
          </div>
        </div>
      )}
    </PanelShell>
  );
}
