"use client";

import { useState } from "react";

import type { Thread, Turn } from "@/lib/api/studio";

/**
 * The run as an exchange rather than as machinery.
 *
 * A span tree says what was called. This says what was asked and what came back
 * -- which is the thing you actually need when a finding looks wrong. Filtered
 * by the node selected on the canvas, so picking `verify` shows the verification
 * conversations and nothing else.
 */

function preview(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function TurnBlock({ turn }: { turn: Turn }) {
  const [openSystem, setOpenSystem] = useState(false);
  const system = turn.messages.find((m) => m.role === "system");
  const rest = turn.messages.filter((m) => m.role !== "system");

  return (
    <article className={`sx-turn ${turn.error ? "is-error" : ""}`}>
      <header className="sx-turn-head">
        <span className="sx-turn-step">{turn.step}</span>
        {turn.tokens ? <span className="sx-turn-meta">{turn.tokens} tok</span> : null}
        {turn.latency_ms !== null && <span className="sx-turn-meta">{(turn.latency_ms / 1000).toFixed(2)}s</span>}
      </header>

      {system && (
        <>
          <button type="button" className="sx-disclose" onClick={() => setOpenSystem((v) => !v)}>
            {openSystem ? "지시문 숨기기" : "지시문 보기"}
          </button>
          {openSystem && <pre className="sx-bubble is-system">{system.content}</pre>}
        </>
      )}

      {rest.map((message, i) => (
        <pre key={i} className={`sx-bubble is-${message.role}`}>
          {message.content}
        </pre>
      ))}

      {turn.reply && <pre className="sx-bubble is-ai">{turn.reply}</pre>}

      {turn.tools.map((tool, i) => (
        <div key={`${tool.name}-${i}`} className="sx-tool">
          <div className="sx-tool-name">
            {tool.name}
            {tool.latency_ms !== null && <span className="sx-turn-meta"> {tool.latency_ms}ms</span>}
          </div>
          <pre className="sx-bubble is-tool">{preview(tool.error ?? tool.outputs)}</pre>
        </div>
      ))}

      {turn.error && <pre className="sx-bubble is-error">{turn.error}</pre>}
    </article>
  );
}

export default function ConversationView({ threads, node }: { threads: Thread[]; node: string | null }) {
  // A turn's `step` is its node, so scoping to the selected node is a filter
  // rather than a second request.
  const shown = node
    ? threads
        .map((t) => ({ ...t, turns: t.turns.filter((turn) => turn.step.startsWith(node)) }))
        .filter((t) => t.turns.length > 0)
    : threads;

  if (shown.length === 0) {
    return <p className="sx-empty">{node ? `${node}에서 오간 대화가 없습니다.` : "기록된 대화가 없습니다."}</p>;
  }

  return (
    <div className="sx-threads">
      {shown.map((thread) => (
        <section key={thread.id} className="sx-thread">
          <h3 className="sx-thread-title">
            {thread.symbol ?? thread.id}
            {thread.file && <span className="sx-thread-file">{thread.file}</span>}
          </h3>
          {thread.turns.map((turn) => (
            <TurnBlock key={turn.id} turn={turn} />
          ))}
        </section>
      ))}
    </div>
  );
}
