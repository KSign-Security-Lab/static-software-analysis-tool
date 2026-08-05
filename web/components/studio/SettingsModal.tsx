"use client";

import { useEffect, useState } from "react";

import { fetchHealth, type AgentHealth } from "@/lib/api/studio";

/**
 * What Studio's Settings modal holds here: what this graph runs on.
 *
 * There are no assistants to pick between -- there is one graph and one model.
 * What is worth checking is whether the endpoint is up and whether the model
 * name matches something it actually serves, which is the usual first failure
 * and invisible until a run dies forty chunks in.
 */

export default function SettingsModal({ onClose }: { onClose: () => void }) {
  const [health, setHealth] = useState<AgentHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [probing, setProbing] = useState(true);

  useEffect(() => {
    // Probed rather than merely read: the answer people want is whether the
    // configured model is one the server actually serves.
    fetchHealth(true)
      .then(setHealth)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setProbing(false));
  }, []);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [onClose]);

  const rows: [string, string][] = health
    ? [
        ["Model", health.model ?? "(미설정)"],
        ["Endpoint", health.base_url],
        ["Reachable", health.reachable ? "yes" : "no"],
        ["Served", health.model_is_served ? "yes" : "no"],
        ["Tools", health.tools_enabled ? `on · ${health.sandbox}` : "off"],
        ["Runs", health.runs_dir],
      ]
    : [];

  return (
    <div className="sx-scrim" onClick={onClose}>
      <div className="sx-modal" role="dialog" aria-label="Settings" onClick={(e) => e.stopPropagation()}>
        <header className="sx-modal-head">
          <h2>Settings</h2>
          <button type="button" className="sx-ghost" onClick={onClose}>
            ✕
          </button>
        </header>

        {probing && <p className="sx-muted">확인 중…</p>}
        {error && <p className="sx-error">{error}</p>}

        {health && (
          <>
            <dl className="sx-kv">
              {rows.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>

            {health.served_models && health.served_models.length > 0 && (
              <p className="sx-muted">서버가 제공하는 모델: {health.served_models.join(", ")}</p>
            )}
            {health.reachable && health.model_is_served === false && (
              <p className="sx-error">
                AGENT_MODEL이 이 서버가 제공하는 이름과 다릅니다. 실행은 시작되지만 첫 모델 호출에서 실패합니다.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
