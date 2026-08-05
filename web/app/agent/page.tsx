"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import SectionHeader from "@/components/shell/SectionHeader";
import Workspace from "@/components/workspace/Workspace";
import type { Finding } from "@/lib/agent-schema";
import {
  agentHealth,
  createEmptyRun,
  deleteFile,
  fetchFile,
  fetchFindings,
  startInspection,
  subscribeToRun,
  uploadSource,
  writeFile,
  type AgentHealth,
  type IndexStats,
} from "@/lib/api/agent";
import { fromAgent, type UiFinding } from "@/lib/model/finding";
import { setCurrentRun } from "@/lib/studio/session";

const SECTION_VIEWS = [
  { href: "/agent", label: "검사" },
  { href: "/agent/studio", label: "트레이스" },
];

const STARTER = `#include <stdlib.h>
#include <stdio.h>

void handle(const char *url) {
    char cmd[128];
    sprintf(cmd, "wget %s", url);
    system(cmd);
}
`;

/**
 * The agent section, as a small IDE.
 *
 * Uploading a tree was the only way in, which made trying one snippet a round
 * trip through the filesystem. You can now paste into an empty run, add files
 * and delete them; each write re-indexes server-side, and because chunk ids are
 * content-derived a re-run only pays for the chunks that changed.
 */
export default function AgentPage() {
  const router = useRouter();
  const [health, setHealth] = useState<AgentHealth | null>(null);
  const [runId, setRunId] = useState<string | null>(null);

  // Handed to the trace view, which traces this session's run rather than
  // every run on the server -- those belong to whoever else is using it.
  useEffect(() => setCurrentRun(runId), [runId]);
  const [files, setFiles] = useState<string[]>([]);
  const [index, setIndex] = useState<IndexStats | null>(null);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [raw, setRaw] = useState<Finding[]>([]);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0, symbol: "" });
  const [error, setError] = useState<string | null>(null);

  const unsubscribe = useRef<(() => void) | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    agentHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
    return () => unsubscribe.current?.();
  }, []);

  const findings: UiFinding[] = fromAgent(raw);

  const openFile = useCallback(
    async (path: string) => {
      if (!runId || path === activeFile) return;
      try {
        const file = await fetchFile(runId, path);
        setActiveFile(file.path);
        setContent(file.content);
        setDirty(false);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [runId, activeFile],
  );

  /** Pasting should not require uploading something first. */
  const ensureRun = useCallback(async (): Promise<string | null> => {
    if (runId) return runId;
    try {
      const run = await createEmptyRun();
      setRunId(run.run_id);
      return run.run_id;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, [runId]);

  const save = useCallback(async () => {
    if (!activeFile) return;
    const id = await ensureRun();
    if (!id) return;
    setSaving(true);
    setError(null);
    try {
      const result = await writeFile(id, activeFile, content);
      setFiles(result.files);
      setIndex(result.index);
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [activeFile, content, ensureRun]);

  const addFile = useCallback(async () => {
    const name = window.prompt("새 파일 이름", "new.c");
    if (!name) return;
    const id = await ensureRun();
    if (!id) return;
    try {
      const result = await writeFile(id, name, "");
      setFiles(result.files);
      setIndex(result.index);
      setActiveFile(name);
      setContent("");
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [ensureRun]);

  const removeFile = useCallback(async () => {
    if (!runId || !activeFile) return;
    if (!window.confirm(`${activeFile} 을(를) 삭제할까요?`)) return;
    try {
      const result = await deleteFile(runId, activeFile);
      setFiles(result.files);
      setIndex(result.index);
      setRaw((prev) => prev.filter((f) => f.primary.file !== activeFile));
      const next = result.files[0] ?? null;
      setActiveFile(next);
      setContent(next ? (await fetchFile(runId, next)).content : "");
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [runId, activeFile]);

  /** A starter buffer, so the section is usable the moment it opens. */
  const startBlank = useCallback(async () => {
    const id = await ensureRun();
    if (!id) return;
    try {
      const result = await writeFile(id, "main.c", STARTER);
      setFiles(result.files);
      setIndex(result.index);
      setActiveFile("main.c");
      setContent(STARTER);
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [ensureRun]);

  const upload = useCallback(async (selected: FileList | null) => {
    if (!selected?.length) return;
    setError(null);
    unsubscribe.current?.();
    setRaw([]);
    setProgress({ done: 0, total: 0, symbol: "" });
    try {
      const result = await uploadSource(Array.from(selected));
      setRunId(result.run_id);
      setFiles(result.files);
      setIndex(result.index);
      const first = result.files.find((f) => /\.(c|h|cpp|cc|java|py|ts|go|rs)$/i.test(f)) ?? result.files[0];
      if (first) {
        const file = await fetchFile(result.run_id, first);
        setActiveFile(file.path);
        setContent(file.content);
        setDirty(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const inspect = useCallback(async () => {
    if (!runId) return;
    if (dirty) await save();
    setError(null);
    setRunning(true);
    setProgress({ done: 0, total: index?.chunks ?? 0, symbol: "" });
    try {
      await startInspection(runId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRunning(false);
      return;
    }

    // Straight to the trace, which is already streaming by the time it paints.
    // The run is now several things at once -- a wave of chunks, four
    // specialists on each -- and watching that happen is the point of having
    // built the view. The subscription below stays attached, so coming back
    // here mid-run still shows the progress bar and the findings as they land.
    router.push("/agent/studio");

    unsubscribe.current?.();
    unsubscribe.current = subscribeToRun(runId, {
      onChunkStarted: ({ total }) => setProgress((p) => ({ ...p, total: total || p.total })),
      onChunkFinished: ({ symbol, findings: fresh, stats }) => {
        setProgress({ done: stats.chunks_inspected ?? 0, total: stats.chunks_total ?? 0, symbol });
        if (fresh.length) {
          setRaw((prev) => {
            const merged = new Map(prev.map((f) => [f.id, f]));
            for (const f of fresh) merged.set(f.id, f);
            return [...merged.values()];
          });
        }
      },
      onFinished: async () => {
        setRunning(false);
        try {
          const report = await fetchFindings(runId);
          setRaw(report.findings ?? []);
        } catch {
          /* streamed findings are already on screen */
        }
      },
      onFailed: ({ error: message }) => {
        setRunning(false);
        setError(message);
      },
    });
  }, [runId, index, dirty, save, router]);

  // Ctrl/Cmd-S: an editor that only saves from a button is annoying.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (dirty) void save();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dirty, save]);

  const percent = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <>
      <SectionHeader title="에이전트" note="청크 단위 LLM 검사" views={SECTION_VIEWS}>
        <button type="button" className="btn" onClick={addFile} disabled={running}>
          + 파일
        </button>
        <button type="button" className="btn" onClick={() => fileInput.current?.click()} disabled={running}>
          업로드
        </button>
        <input ref={fileInput} type="file" multiple hidden onChange={(e) => upload(e.target.files)} />
        <button type="button" className="btn" onClick={save} disabled={!dirty || saving}>
          {saving ? "저장 중…" : dirty ? "저장 ⌘S" : "저장됨"}
        </button>
        <button type="button" className="btn btn-primary" onClick={inspect} disabled={!runId || running}>
          {running ? "검사 중…" : "검사 실행"}
        </button>
        {index?.chunks !== undefined && (
          <span className="target-stats">
            파일 {files.length} · 청크 {index.chunks} · 결과 {findings.length}
          </span>
        )}
        {runId && (
          // Watchable while the run is still going: the studio fills in live.
          <a className="btn btn-ghost" href={`/agent/studio?run=${runId}`}>
            트레이스 ↗
          </a>
        )}
        {health && !health.configured && <span className="target-warn">모델 미설정 (AGENT_MODEL)</span>}
      </SectionHeader>

      <Workspace
        files={files}
        activeFile={activeFile}
        fileContent={content}
        findings={findings}
        onOpenFile={openFile}
        editable
        onEdit={(value) => {
          setContent(value);
          setDirty(true);
        }}
        onDeleteFile={activeFile ? removeFile : undefined}
        placeholder={
          <div className="ws-empty-lg">
            <p>붙여넣거나, 파일을 추가하거나, 트리를 업로드하세요.</p>
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" className="btn btn-primary" onClick={startBlank}>
                예제로 시작
              </button>
              <button type="button" className="btn" onClick={addFile}>
                빈 파일 만들기
              </button>
            </div>
          </div>
        }
        emptyHint={running ? "검사 중…" : "‘검사 실행’을 눌러 이 코드를 검사하세요."}
        status={
          <>
            {error && <div className="ws-error">{error}</div>}
            {(running || progress.done > 0) && (
              <div className="ws-progress">
                <div className="ws-progress-bar">
                  <div className="ws-progress-fill" style={{ width: `${percent}%` }} />
                </div>
                <span className="ws-progress-text">
                  {progress.done} / {progress.total} 청크{progress.symbol && ` · ${progress.symbol}`}
                </span>
              </div>
            )}
          </>
        }
      />
    </>
  );
}
