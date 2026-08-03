"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CodeEditor } from "@/components/inspect/CodeEditor";
import { FileTree } from "@/components/inspect/FileTree";
import { FindingList } from "@/components/inspect/FindingList";
import { FindingPanel } from "@/components/inspect/FindingPanel";
import { RunProgress } from "@/components/inspect/RunProgress";
import {
  agentHealth,
  fetchFile,
  fetchFindings,
  startInspection,
  subscribeToRun,
  uploadSource,
  type AgentHealth,
  type IndexStats,
} from "@/lib/agent-api";
import type { Finding, SeverityName } from "@/lib/agent-schema";
import { SEVERITIES } from "@/lib/agent-schema";
import { countsByFile } from "@/lib/markers";

/**
 * Upload source, read it in an editor, inspect it, and see the findings inline.
 *
 * The page has two jobs and does them in order: it is a working code viewer
 * before anything has been analysed, and it becomes an annotated one after.
 * Findings arrive over SSE as each chunk is confirmed, because a run over a
 * real tree takes minutes and a page that shows nothing for five minutes looks
 * broken.
 */

interface FileState {
  path: string;
  content: string;
  language: string;
}

export default function InspectPage() {
  const [health, setHealth] = useState<AgentHealth | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [files, setFiles] = useState<string[]>([]);
  const [indexStats, setIndexStats] = useState<IndexStats | null>(null);
  const [active, setActive] = useState<FileState | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<Set<SeverityName>>(
    () => new Set(SEVERITIES),
  );

  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0, current: null as string | null });
  const [error, setError] = useState<string | null>(null);

  const unsubscribe = useRef<(() => void) | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    agentHealth().then(setHealth).catch(() => setHealth(null));
    return () => unsubscribe.current?.();
  }, []);

  const selected = useMemo(
    () => findings.find((f) => f.id === selectedId) ?? null,
    [findings, selectedId],
  );
  const counts = useMemo(() => countsByFile(findings), [findings]);

  const openFile = useCallback(
    async (path: string) => {
      if (!runId) return;
      try {
        const file = await fetchFile(runId, path);
        setActive({ path: file.path, content: file.content, language: file.language });
      } catch (err) {
        setError(String(err));
      }
    },
    [runId],
  );

  const handleUpload = useCallback(async (selectedFiles: FileList | null) => {
    if (!selectedFiles || selectedFiles.length === 0) return;
    setUploading(true);
    setError(null);
    unsubscribe.current?.();
    setFindings([]);
    setSelectedId(null);
    setProgress({ done: 0, total: 0, current: null });

    try {
      const result = await uploadSource(Array.from(selectedFiles));
      setRunId(result.run_id);
      setFiles(result.files);
      setIndexStats(result.index);
      setActive(null);
      // Open something immediately: the page is a viewer before it is a report.
      const first = result.files.find((f) => /\.(c|h|cpp|java|py|ts|go|rs)$/i.test(f));
      if (first) {
        const file = await fetchFile(result.run_id, first);
        setActive({ path: file.path, content: file.content, language: file.language });
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setUploading(false);
    }
  }, []);

  const handleInspect = useCallback(async () => {
    if (!runId) return;
    setError(null);
    setRunning(true);
    setProgress({ done: 0, total: indexStats?.chunks ?? 0, current: null });

    try {
      await startInspection(runId);
    } catch (err) {
      setError(String(err));
      setRunning(false);
      return;
    }

    unsubscribe.current?.();
    unsubscribe.current = subscribeToRun(runId, {
      // The first event is the only place the queue length is known before any
      // chunk has finished, so the bar has a denominator from the start.
      onChunkStarted: ({ total }) =>
        setProgress((prev) => ({ ...prev, total: total || prev.total })),
      onChunkFinished: ({ symbol, findings: fresh, stats }) => {
        setProgress({
          done: stats.chunks_inspected ?? 0,
          total: stats.chunks_total ?? 0,
          current: symbol,
        });
        if (fresh.length > 0) {
          // Merge by id: a re-run of the same chunk must not duplicate rows.
          setFindings((prev) => {
            const merged = new Map(prev.map((f) => [f.id, f]));
            for (const finding of fresh) merged.set(finding.id, finding);
            return Array.from(merged.values());
          });
        }
      },
      onFinished: async () => {
        setRunning(false);
        setProgress((prev) => ({ ...prev, current: null }));
        try {
          const report = await fetchFindings(runId);
          setFindings(report.findings ?? []);
        } catch {
          /* the streamed findings are already on screen */
        }
      },
      onFailed: ({ error: message }) => {
        setRunning(false);
        setError(message);
      },
    });
  }, [runId, indexStats]);

  const navigateTo = useCallback(
    async (file: string, line: number) => {
      if (file !== active?.path) await openFile(file);
      // The editor reveals the line itself when `selected` changes; this only
      // has to make sure the right file is open.
      void line;
    },
    [active, openFile],
  );

  const toggleSeverity = useCallback((severity: SeverityName) => {
    setSeverityFilter((prev) => {
      const next = new Set(prev);
      if (next.has(severity)) next.delete(severity);
      else next.add(severity);
      return next;
    });
  }, []);

  const selectFinding = useCallback(
    async (finding: Finding) => {
      setSelectedId(finding.id);
      if (finding.primary.file !== active?.path) await openFile(finding.primary.file);
    },
    [active, openFile],
  );

  return (
    <main className="inspect">
      <header className="inspect-head">
        <div className="inspect-brand">
          <h1>코드 검사</h1>
          <p className="subtle">소스를 업로드하고 청크 단위로 취약점을 검사합니다.</p>
        </div>

        <div className="inspect-actions">
          <input
            ref={fileInput}
            type="file"
            multiple
            hidden
            onChange={(event) => handleUpload(event.target.files)}
          />
          <button
            type="button"
            className="btn"
            onClick={() => fileInput.current?.click()}
            disabled={uploading || running}
          >
            {uploading ? "업로드 중…" : "소스 업로드"}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleInspect}
            disabled={!runId || running || uploading}
            title={health?.configured === false ? "모델이 설정되지 않았습니다" : undefined}
          >
            {running ? "검사 중…" : "검사 실행"}
          </button>
        </div>
      </header>

      {health && !health.configured && (
        <div className="banner banner-warn">
          모델이 설정되지 않았습니다. <code>AGENT_MODEL</code>과 <code>AGENT_BASE_URL</code>을
          설정한 뒤 API를 다시 시작하세요. (현재 엔드포인트: <code>{health.base_url}</code>)
        </div>
      )}

      {indexStats && (
        <div className="index-summary">
          파일 {indexStats.files_indexed}개 · 청크 {indexStats.chunks}개 · 연결{" "}
          {indexStats.links}개
          {indexStats.files_skipped > 0 && ` · 건너뜀 ${indexStats.files_skipped}개`}
        </div>
      )}

      <RunProgress
        running={running}
        done={progress.done}
        total={progress.total}
        current={progress.current}
        findings={findings.length}
        error={error}
      />

      <div className="inspect-body">
        <div className="inspect-left">
          <FileTree
            files={files}
            selected={active?.path ?? null}
            counts={counts}
            onSelect={openFile}
          />
          <FindingList
            findings={findings}
            selectedId={selectedId}
            severityFilter={severityFilter}
            onToggleSeverity={toggleSeverity}
            onSelect={selectFinding}
          />
        </div>

        <div className="inspect-center">
          <CodeEditor
            path={active?.path ?? null}
            content={active?.content ?? ""}
            language={active?.language ?? "plaintext"}
            findings={findings}
            selected={selected}
            onSelectFinding={setSelectedId}
          />
        </div>

        <FindingPanel
          finding={selected}
          onNavigate={navigateTo}
          onClose={() => setSelectedId(null)}
        />
      </div>
    </main>
  );
}
