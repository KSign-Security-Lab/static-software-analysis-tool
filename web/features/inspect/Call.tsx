"use client";

import { CodeBlock } from "@/components/panel/code-block";
import { Payload } from "@/features/trace/Payload";
import { Badge } from "@/components/ui/badge";
import type { Exchange } from "@/lib/trace/process";

/**
 * One recorded call, as it happened.
 *
 * Read-only, and that is the whole change from what was here before: this used
 * to be the prompt studio, with a replay button and an editable system prompt.
 * Tuning a prompt from a browser is gone with the endpoints it used -- it belongs
 * to `agent.tuner`, which replays a recorded run before it proposes anything,
 * which a PUT from a page could not do.
 *
 * What is left is the part a reader of a finding actually wants: what it was
 * asked, what it called, and what it said.
 */
export default function Call({ exchange }: { exchange: Exchange }) {
  return (
    <div className="mt-1 mb-2 ml-5 space-y-2 rounded-md border border-line bg-field px-2.5 py-2">
      {exchange.attempts > 1 && (
        <p className="text-2xs text-ink-faint">
          {/* Not a retry to be alarmed about: a structured call falls back to a
              second method, and `gather` is a loop by design. */}
          모델 호출 {exchange.attempts}회
          {exchange.retried > 0 && ` · 다시 시도 ${exchange.retried}회`}
        </p>
      )}

      <Field label="지시">
        <CodeBlock text={exchange.system} />
      </Field>
      <Field label="물어본 것">
        <CodeBlock text={exchange.user} />
      </Field>

      {exchange.calls.length > 0 && (
        <Field label="부른 도구">
          <ul className="space-y-1.5">
            {exchange.calls.map((call, index) => (
              <li key={`${call.name}:${index}`} className="space-y-0.5">
                <p className="flex items-baseline gap-1.5">
                  <span className="font-mono text-2xs text-ink-strong">{call.name}</span>
                  {call.latency_ms !== null && (
                    <span className="font-mono text-2xs text-ink-faint">{call.latency_ms}ms</span>
                  )}
                </p>
                <Payload value={call.args} />
                <Payload value={call.outputs} />
              </li>
            ))}
          </ul>
        </Field>
      )}

      {exchange.reply && (
        <Field label="답">
          <Payload value={exchange.reply} />
        </Field>
      )}

      {exchange.error && (
        <Field label="오류">
          <p className="text-2xs text-danger">{exchange.error}</p>
        </Field>
      )}

      {exchange.offered.length > 0 && (
        <p className="flex flex-wrap gap-1">
          {/* What it was allowed to call, whether or not it did. A specialist
              that could have read more source and chose not to is a different
              thing from one that was never offered the option. */}
          {exchange.offered.map((tool) => (
            <Badge key={tool.name} variant="outline" className="font-mono text-2xs font-normal text-ink-faint">
              {tool.name}
            </Badge>
          ))}
        </p>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <p className="text-2xs font-semibold tracking-wide text-ink-faint">{label}</p>
      {children}
    </div>
  );
}
