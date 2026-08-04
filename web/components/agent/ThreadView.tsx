"use client";

import { useState } from "react";

import type { Thread, Turn } from "@/lib/api/agent";

/**
 * The run as conversations, one per chunk.
 *
 * The span tree shows the machinery; this shows the exchange. A chunk is the
 * unit the agent reasons in -- analyse it, gather evidence about what it found,
 * rule on it -- so that is the thread, and each model call is a turn in it.
 */

const ROLE_LABEL: Record<string, string> = {
  system: "지시",
  human: "입력",
  ai: "모델",
  tool: "도구 결과",
};

function roleClass(role: string): string {
  if (role === "system") return "is-system";
  if (role === "ai" || role === "assistant") return "is-ai";
  if (role === "tool") return "is-tool";
  return "is-human";
}

function pretty(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function TurnBlock({ turn }: { turn: Turn }) {
  // The system prompt is identical across every turn of a step; collapsed by
  // default so the actual exchange is what you see.
  const [showSystem, setShowSystem] = useState(false);
  const messages = turn.messages.filter((m) => showSystem || m.role !== "system");
  const hasSystem = turn.messages.some((m) => m.role === "system");

  return (
    <div className={`turn ${turn.error ? "is-error" : ""}`}>
      <div className="turn-head">
        <span className="turn-step">{turn.step}</span>
        {turn.latency_ms !== null && <span className="span-ms">{(turn.latency_ms / 1000).toFixed(2)}s</span>}
        {turn.tokens ? <span className="span-tok">{turn.tokens} tok</span> : null}
        {hasSystem && (
          <button type="button" className="chip" onClick={() => setShowSystem((v) => !v)}>
            {showSystem ? "지시 숨기기" : "지시 보기"}
          </button>
        )}
      </div>

      {messages.map((message, i) => (
        <div key={i} className={`bubble ${roleClass(message.role)}`}>
          <div className="bubble-role">{ROLE_LABEL[message.role] ?? message.role}</div>
          <pre className="bubble-body">{message.content}</pre>
        </div>
      ))}

      {turn.tools.map((tool, i) => (
        <div key={`${tool.name}-${i}`} className="bubble is-tool">
          <div className="bubble-role">
            도구 · {tool.name}
            {tool.latency_ms !== null && <span className="span-ms"> {tool.latency_ms}ms</span>}
          </div>
          <pre className="bubble-args">{pretty(tool.inputs)}</pre>
          <pre className="bubble-body">{tool.error ?? pretty(tool.outputs)}</pre>
        </div>
      ))}

      {turn.reply && (
        <div className="bubble is-ai">
          <div className="bubble-role">모델</div>
          <pre className="bubble-body">{turn.reply}</pre>
        </div>
      )}

      {turn.error && <pre className="span-io">{turn.error}</pre>}
    </div>
  );
}

export default function ThreadView({ threads }: { threads: Thread[] }) {
  const [open, setOpen] = useState<string | null>(threads[0]?.id ?? null);
  const thread = threads.find((t) => t.id === open) ?? threads[0] ?? null;

  if (!thread) return <p className="ws-empty">아직 대화가 없습니다.</p>;

  return (
    <div className="threads">
      <aside className="threads-list">
        {threads.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`thread-tab ${t.id === thread.id ? "is-selected" : ""}`}
            onClick={() => setOpen(t.id)}
          >
            <span className="thread-tab-name">{t.symbol ?? t.id}</span>
            <span className="trace-run-meta">
              {t.turns.length}턴 · {t.tokens.toLocaleString()} tok
            </span>
          </button>
        ))}
      </aside>
      <div className="thread-body">
        <div className="ws-pane-title">
          <span>
            {thread.symbol ?? thread.id}
            {thread.file && thread.file !== thread.symbol ? ` · ${thread.file}` : ""}
          </span>
          <span className="span-tok">{thread.turns.length}턴</span>
        </div>
        <div className="thread-scroll">
          {thread.turns.map((turn) => (
            <TurnBlock key={turn.id} turn={turn} />
          ))}
        </div>
      </div>
    </div>
  );
}
