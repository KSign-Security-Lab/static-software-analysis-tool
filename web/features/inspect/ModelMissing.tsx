"use client";

import { AlertTriangle } from "lucide-react";

import type { AgentHealth } from "@/lib/api/types";

export default function ModelMissing({ health }: { health: AgentHealth | undefined }) {
  if (!health || health.configured) return null;

  const served = health.served_models ?? [];

  return (
    <div
      role="alert"
      className="mt-6 space-y-1.5 rounded-md border border-warn/40 bg-warn-wash px-3 py-2.5"
    >
      <p className="flex items-center gap-1.5 text-xs font-medium text-ink">
        <AlertTriangle className="size-3.5 shrink-0 text-warn" aria-hidden />
        모델이 설정되지 않아 검사를 시작할 수 없습니다
      </p>
      {served.length > 0 ? (
        <p className="text-2xs leading-relaxed text-ink-muted">
          엔드포인트(<code className="font-mono">{health.base_url}</code>)는{" "}
          {served.map((id, at) => (
            <span key={id}>
              {at > 0 && ", "}
              <code className="font-mono text-ink-strong">{id}</code>
            </span>
          ))}{" "}
          을 서비스하고 있습니다. <code className="font-mono">AGENT_MODEL</code> 을 그중 하나로 지정한 뒤 API를 다시
          띄우십시오.
        </p>
      ) : (
        <p className="text-2xs leading-relaxed text-ink-muted">
          엔드포인트(<code className="font-mono">{health.base_url}</code>)가 응답하지 않아 어떤 모델을 쓸 수 있는지도
          알 수 없습니다. 모델 서버가 떠 있는지 먼저 확인하십시오.
        </p>
      )}
      <p className="text-2xs leading-relaxed text-ink-faint">
        기본값은 일부러 없습니다 — 엉뚱한 모델은 그럴듯한 헛소리를 조용히 만들어 냅니다. 코드를 올려 두는 것은 지금도
        됩니다.
      </p>
    </div>
  );
}
