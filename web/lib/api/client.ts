import { ownerHeaders } from "@/lib/run/whoami";

const API_PORT = process.env.NEXT_PUBLIC_API_PORT || "8001";

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

  get offline(): boolean {
    return this.status === 0;
  }
}

export function seg(value: string): string {
  return encodeURIComponent(value);
}

export interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number | null;
}

export const DEFAULT_TIMEOUT_MS = 30_000;

function deadline(signal: AbortSignal | undefined, ms: number | null): AbortSignal | undefined {
  if (ms === null) return signal;
  const timeout = AbortSignal.timeout(ms);
  if (!signal) return timeout;
  return typeof AbortSignal.any === "function" ? AbortSignal.any([signal, timeout]) : timeout;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {},
): Promise<T> {
  const base = apiBase();
  let res: Response;
  try {
    const headers = { ...ownerHeaders(), ...(init.headers as Record<string, string>) };
    res = await fetch(`${base}${path}`, {
      ...init,
      headers,
      signal: deadline(options.signal, options.timeoutMs === undefined ? DEFAULT_TIMEOUT_MS : options.timeoutMs),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new ApiError(`백엔드(${base})가 응답하지 않습니다. 실행 중인지 확인하세요.`, 0);
    }
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(`백엔드(${base})에 연결할 수 없습니다. 실행 중인지 확인하세요. [${String(err)}]`, 0);
  }

  const text = await res.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
  }

  if (!res.ok) {
    const detail = (body as { detail?: string })?.detail ?? text ?? `${res.status} ${res.statusText}`;
    throw new ApiError(detail, res.status);
  }
  return body as T;
}

const json = { "Content-Type": "application/json" };

export function get<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return request<T>(path, {}, options);
}

export function post<T>(path: string, payload?: unknown, options: RequestOptions = {}): Promise<T> {
  return request<T>(path, { method: "POST", headers: json, body: JSON.stringify(payload ?? {}) }, options);
}

export function put<T>(path: string, payload: unknown, options: RequestOptions = {}): Promise<T> {
  return request<T>(path, { method: "PUT", headers: json, body: JSON.stringify(payload) }, options);
}

export function del<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return request<T>(path, { method: "DELETE" }, options);
}

export function postForm<T>(path: string, form: FormData, options: RequestOptions = {}): Promise<T> {
  return request<T>(path, { method: "POST", body: form }, options);
}

export async function postBlob(
  path: string,
  payload?: unknown,
  options: RequestOptions = {},
): Promise<{ blob: Blob; filename: string | null; headers: Headers }> {
  const base = apiBase();
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, {
      method: "POST",
      headers: { ...ownerHeaders(), ...json },
      body: JSON.stringify(payload ?? {}),
      signal: deadline(options.signal, options.timeoutMs === undefined ? DEFAULT_TIMEOUT_MS : options.timeoutMs),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new ApiError(`백엔드(${base})가 응답하지 않습니다. 실행 중인지 확인하세요.`, 0);
    }
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(`백엔드(${base})에 연결할 수 없습니다. 실행 중인지 확인하세요. [${String(err)}]`, 0);
  }

  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      detail = (JSON.parse(text) as { detail?: string })?.detail ?? text;
    } catch {
    }
    throw new ApiError(detail || `${res.status} ${res.statusText}`, res.status);
  }

  return {
    blob: await res.blob(),
    filename: filenameOf(res.headers.get("content-disposition")),
    headers: res.headers,
  };
}

function filenameOf(disposition: string | null): string | null {
  const found = disposition?.match(/filename="?([^";]+)"?/);
  return found ? found[1] : null;
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function streamUrl(path: string): string {
  return `${apiBase()}${path}`;
}

export function describeError(err: unknown): string {
  if (!(err instanceof ApiError)) return err instanceof Error ? err.message : String(err);
  if (err.offline) return err.message;

  const detail = err.message;
  switch (err.status) {
    case 404:
      return `찾을 수 없습니다. ${detail}`;
    case 409:
      if (/model/i.test(detail)) return "모델이 설정되지 않았습니다. 설정에서 엔드포인트를 확인하세요.";
      if (/breakpoint|interrupt/i.test(detail)) return "중단점에 멈춰 있지 않아 이어서 실행할 수 없습니다.";
      if (/history/i.test(detail)) return "덮어쓸 실행 기록이 없습니다.";
      return detail;
    case 400:
      return detail;
    case 503:
      if (/model/i.test(detail)) return "모델이 설정되지 않았습니다. 설정에서 엔드포인트를 확인하세요.";
      return detail;
    default:
      return detail;
  }
}
