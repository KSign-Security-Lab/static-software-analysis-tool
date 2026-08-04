/**
 * The one place the browser talks to the backend.
 *
 * There used to be two of these -- lib/api.ts and lib/agent-api.ts -- each with
 * its own base-URL resolution, error unwrapping and message wording, so the
 * same failure read differently depending on which half of the app you were in.
 */

const API_PORT = process.env.NEXT_PUBLIC_API_PORT || "8000";

/**
 * Resolved at call time, not module load: the page may be opened on localhost,
 * a LAN address or a tailnet peer, and the API is on the same host.
 */
export function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  if (configured) return configured;
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:${API_PORT}`;
  }
  return `http://localhost:${API_PORT}`;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = apiBase();
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, init);
  } catch (err) {
    // A dead backend is the most common failure and the least self-evident, so
    // it says where it looked rather than "Failed to fetch".
    throw new ApiError(`백엔드(${base})에 연결할 수 없습니다. 실행 중인지 확인하세요. [${String(err)}]`, 0);
  }

  const text = await res.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
    /* error bodies are not always JSON */
  }

  if (!res.ok) {
    const detail = (body as { detail?: string })?.detail ?? text ?? `${res.status} ${res.statusText}`;
    throw new ApiError(detail, res.status);
  }
  return body as T;
}

export function get<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function post<T>(path: string, payload: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function postForm<T>(path: string, form: FormData): Promise<T> {
  return request<T>(path, { method: "POST", body: form });
}

export function streamUrl(path: string): string {
  return `${apiBase()}${path}`;
}
