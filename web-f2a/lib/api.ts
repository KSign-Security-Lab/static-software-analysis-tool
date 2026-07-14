import type { AnalyzeResponse } from "./types";

// Resolve the backend base URL at runtime so it works from whatever host the
// page was opened on (localhost, the Tailscale IP, any tailnet peer). Override
// with NEXT_PUBLIC_API_URL if the backend lives elsewhere.
const API_PORT = process.env.NEXT_PUBLIC_API_PORT || "8000";

export function apiBase(): string {
  const env = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  if (env) return env;
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:${API_PORT}`;
  }
  return `http://localhost:${API_PORT}`;
}

export interface AnalyzeInput {
  source: string;
  language: string;
  filename?: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const base = apiBase();
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    throw new Error(
      `F2-A 백엔드(${base})에 연결할 수 없습니다. 이 호스트에서 실행 중인가요? ` +
        `(uv run uvicorn api.main:app --host 0.0.0.0 --port ${API_PORT} --app-dir .)  [${String(err)}]`,
    );
  }
  const text = await res.text();
  let data: unknown = undefined;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    /* non-JSON error body */
  }
  if (!res.ok) {
    const detail =
      (data as { detail?: string })?.detail ?? text ?? `${res.status} ${res.statusText}`;
    throw new Error(detail);
  }
  return data as T;
}

export function analyze(input: AnalyzeInput): Promise<AnalyzeResponse> {
  return post<AnalyzeResponse>("/analyze", input);
}

export async function checkHealth(): Promise<{ status: string; joern_container: string }> {
  const res = await fetch(`${apiBase()}/health`);
  if (!res.ok) throw new Error(`health ${res.status}`);
  return res.json();
}
