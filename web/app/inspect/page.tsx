"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import Workspace from "@/components/workspace/Workspace";
import {
  agentHealth,
  fetchFile,
  fetchFindings,
  startInspection,
  subscribeToRun,
  uploadSource,
  type AgentHealth,
  type IndexStats,
} from "@/lib/api/agent";
import type { Finding } from "@/lib/agent-schema";
import { fromAgent, type UiFinding } from "@/lib/model/finding";

/**
 * LLM inspection, on the same workspace the structural page uses.
 *
 * The engines are still independent -- this uploads its own tree and runs its
 * own pipeline -- but a finding is read exactly the same way on both pages.
 */
export default function InspectPage() {
  const [health, setHealth] = useState<AgentHealth | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [files, setFiles] = useState<string[]>([]);
  const [index, setIndex] = useState<IndexStats | null>(null);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [raw, setRaw] = useState<Finding[]>([]);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0, symbol: "" });
  const [error, setError] = useState<string | null>(null);

  const unsubscribe = useRef<(() => void) | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    agentHealth().then(setHealth).catch(() => setHealth(null));
    return () => unsubscribe.current?.();
  }, []);

  const findings: UiFinding[] = fromAgent(raw);

  const openFile = useCallback(
    async (path: string) => {
      if (!runId) return;
      try {
        const file = await fetchFile(runId, path);
        setActiveFile(file.path);
        setContent(file.content);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [runId],
  );

  const upload = useCallback(
    async (selected: FileList | null) => {
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
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [],
  );

  const inspect = useCallback(async () => {
    if (!runId) return;
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

    unsubscribe.current?.();
    unsubscribe.current = subscribeToRun(runId, {
      onChunkStarted: ({ total }) => setProgress((p) => ({ ...p, total: total || p.total })),
      onChunkFinished: ({ symbol, findings: fresh, stats }) => {
        setProgress({ done: stats.chunks_inspected ?? 0, total: stats.chunks_total ?? 0, symbol });
        if (fresh.length) {
          // Merge by id so a re-inspected chunk does not duplicate rows.
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
  }, [runId, index]);

  const percent = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <Workspace
      files={files}
      activeFile={activeFile}
      fileContent={content}
      findings={findings}
      onOpenFile={openFile}
      toolbar={
        <div className="target">
          <button type="button" className="btn" onClick={() => fileInput.current?.click()} disabled={running}>
            소스 업로드
          </button>
          <input
            ref={fileInput}
            type="file"
            multiple
            hidden
            onChange={(e) => upload(e.target.files)}
          />
          <button type="button" className="btn btn-primary" onClick={inspect} disabled={!runId || running}>
            {running ? "검사 중…" : "검사 실행"}
          </button>
          {index && (
            <span className="target-stats">
              파일 {index.files_indexed} · 청크 {index.chunks} · 결과 {findings.length}
            </span>
          )}
          {health && !health.configured && <span className="target-warn">모델 미설정 (AGENT_MODEL)</span>}
          {health?.tracing?.enabled && <span className="target-hint">추적 → {health.tracing.project}</span>}
        </div>
      }
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
  );
}
