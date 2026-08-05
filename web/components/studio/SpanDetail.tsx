"use client";

import { useEffect, useMemo, useState } from "react";

import { replaySpan, resetPrompt, savePrompt, type PromptRow, type Replay, type Span } from "@/lib/api/studio";

/**
 * One call, and the loop for making it better.
 *
 * Read what the model was told and what it said, change the prompt, run just
 * that call again, and put the two answers side by side. Nothing here touches
 * the run: the trace stays the record of what happened, so the same prompt can
 * be tried ten times against the same real input.
 *
 * When an edit is worth keeping, `프롬프트로 저장` writes it to the override
 * store and every later run uses it.
 */

function text(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

/** What a model call recorded, however LangChain spelled it. */
function recorded(span: Span): { system: string; user: string } {
  const inputs = (span.inputs ?? {}) as { messages?: { role: string; content: string }[]; prompts?: string[] };
  if (Array.isArray(inputs.messages)) {
    return {
      system: inputs.messages.find((m) => m.role === "system")?.content ?? "",
      user: inputs.messages.find((m) => m.role === "human" || m.role === "user")?.content ?? "",
    };
  }
  return { system: "", user: inputs.prompts?.[0] ?? "" };
}

function replyOf(span: Span): string {
  const outputs = (span.outputs ?? {}) as { text?: string[] };
  if (Array.isArray(outputs.text)) return outputs.text.join("\n");
  return text(span.outputs);
}

export default function SpanDetail({
  runId,
  span,
  prompts,
  onPrompts,
}: {
  runId: string;
  span: Span | null;
  prompts: PromptRow[];
  onPrompts: (rows: PromptRow[]) => void;
}) {
  const [system, setSystem] = useState("");
  const [user, setUser] = useState("");
  const [result, setResult] = useState<Replay | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const original = useMemo(() => (span ? recorded(span) : { system: "", user: "" }), [span]);

  // A new span replaces the draft: an edit belongs to the call it was made
  // against, and carrying it over would silently test it on another input.
  useEffect(() => {
    setSystem(original.system);
    setUser(original.user);
    setResult(null);
    setError(null);
  }, [span?.id, original.system, original.user]);

  if (!span) {
    return <p className="sx-muted sx-pad">트레이스에서 호출을 선택하세요.</p>;
  }

  const isModelCall = span.kind === "llm";
  const step = String(span.meta?.step ?? "");
  const tunable = prompts.find((p) => p.name === step);
  const edited = system !== original.system || user !== original.user;

  const run = () => {
    setBusy(true);
    setError(null);
    replaySpan(runId, span.id, { system, user })
      .then(setResult)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setBusy(false));
  };

  const adopt = () => {
    if (!tunable) return;
    setBusy(true);
    setError(null);
    savePrompt(tunable.name, system)
      .then((d) => onPrompts(d.prompts))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setBusy(false));
  };

  const revert = () => {
    if (!tunable) return;
    setBusy(true);
    resetPrompt(tunable.name)
      .then((d) => {
        onPrompts(d.prompts);
        const back = d.prompts.find((p) => p.name === tunable.name);
        if (back) setSystem(back.in_use);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setBusy(false));
  };

  return (
    <div className="tx-detail">
      <header className="tx-detail-head">
        <span className="tx-detail-name">{span.name}</span>
        <span className="tx-detail-meta">
          {span.status === "running" ? "진행 중" : `${span.latency_ms ?? 0}ms`}
          {span.tokens ? ` · ${span.tokens} tok` : ""}
          {step ? ` · ${step}` : ""}
        </span>
      </header>

      {span.error && <pre className="sx-bubble is-error">{span.error}</pre>}

      {!isModelCall ? (
        <>
          <div className="sx-role">입력</div>
          <pre className="sx-bubble">{text(span.inputs)}</pre>
          <div className="sx-role">출력</div>
          <pre className="sx-bubble">{text(span.outputs)}</pre>
        </>
      ) : (
        <>
          <div className="tx-field">
            <div className="tx-field-head">
              <span className="sx-role">System</span>
              {tunable?.override && <span className="tx-tuned">수정됨</span>}
            </div>
            <textarea
              className="sx-raw tx-prompt"
              value={system}
              spellCheck={false}
              onChange={(e) => setSystem(e.target.value)}
            />
          </div>

          <div className="tx-field">
            <div className="tx-field-head">
              <span className="sx-role">User</span>
              <span className="sx-muted">이 호출이 실제로 받은 입력</span>
            </div>
            <textarea
              className="sx-raw tx-prompt is-user"
              value={user}
              spellCheck={false}
              onChange={(e) => setUser(e.target.value)}
            />
          </div>

          <div className="tx-actions">
            <button type="button" className="sx-submit" disabled={busy} onClick={run}>
              {busy ? "실행 중…" : "다시 실행"}
            </button>
            {edited && (
              <button
                type="button"
                className="sx-ghost"
                onClick={() => {
                  setSystem(original.system);
                  setUser(original.user);
                }}
              >
                되돌리기
              </button>
            )}
            {tunable && (
              <button
                type="button"
                className="sx-ghost"
                disabled={busy || system === tunable.in_use}
                onClick={adopt}
                title={`이후 모든 실행이 이 ${step} 프롬프트를 사용합니다`}
              >
                {step} 프롬프트로 저장
              </button>
            )}
            {tunable?.override && (
              <button type="button" className="sx-ghost" disabled={busy} onClick={revert}>
                기본값 복원
              </button>
            )}
          </div>

          {error && <p className="sx-error">{error}</p>}

          <div className="tx-outputs">
            <div className="tx-output">
              <div className="sx-role">기록된 출력</div>
              <pre className="sx-bubble">{replyOf(span)}</pre>
            </div>
            <div className="tx-output">
              <div className="sx-role">
                새 출력
                {result && <span className="tx-detail-meta"> · {result.latency_ms}ms</span>}
              </div>
              {result ? (
                <pre className={`sx-bubble ${result.output === null ? "is-error" : "is-ai"}`}>
                  {result.output === null ? "모델이 이 스키마를 만족하는 답을 내지 못했습니다." : text(result.output)}
                </pre>
              ) : (
                <p className="sx-muted sx-pad">
                  프롬프트를 고치고 <b>다시 실행</b>하면 여기에 나옵니다. 실행 기록은 그대로 남습니다.
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
