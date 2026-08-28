/**
 * The one place the browser talks to the backend.
 *
 * There used to be two of these, each with its own base-URL resolution, error
 * unwrapping and message wording, so the same failure read differently
 * depending on which half of the app you were in.
 */

import { ownerHeaders } from "@/lib/run/whoami";

const API_PORT = process.env.NEXT_PUBLIC_API_PORT || "8000";

/**
 * Resolved at call time, not module load: the page may be opened on localhost,
 * a LAN address or a tailnet peer, and the API is on the same host. Resolving
 * once at import would freeze whichever of those happened to load first.
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

  /** No response at all, as opposed to a response that said no. */
  get offline(): boolean {
    return this.status === 0;
  }
}

/**
 * A path segment, escaped.
 *
 * Prompt names contain a colon (`lens:memory`). Unescaped happens to work,
 * because Starlette's default converter matches anything but `/`, and escaped
 * works too because it decodes -- but relying on that is how one call site
 * ends up different from the others.
 */
export function seg(value: string): string {
  return encodeURIComponent(value);
}

export interface RequestOptions {
  /** React Query hands one to every queryFn; pass it through and cancellation works. */
  signal?: AbortSignal;
  /**
   * How long to wait for an answer. `null` waits for ever.
   *
   * Defaults to {@link DEFAULT_TIMEOUT_MS}, and the default exists because of a
   * failure mode that had no error at all: a backend whose socket is open while
   * nothing serves it -- uvicorn's reloader parent outliving its worker is the
   * everyday way to get there -- *accepts* the connection and never replies. The
   * fetch neither resolves nor rejects, so every query sat pending, the screen
   * showed skeletons for ever, and nothing said the server was gone.
   *
   * Overridden upward by the handful of calls that are legitimately slow: a
   * clone, an upload of a real tree, an LLM asked for a fix. A blanket 30s would
   * cancel those mid-flight, which is a worse bug than the one being fixed.
   */
  timeoutMs?: number | null;
}

/**
 * The wait after which a backend is presumed gone rather than slow.
 *
 * Generous for a read: everything on the default path is a database query
 * against localhost. Anything that can honestly take longer says so at its call
 * site.
 */
export const DEFAULT_TIMEOUT_MS = 30_000;

/**
 * One signal that fires on either the caller's cancellation or the deadline.
 *
 * `AbortSignal.any` is Safari 17.4 and Chrome 116, which is newer than some of
 * what this is opened in, so its absence falls back to the timeout alone --
 * losing React Query's cancellation, which wastes a request, rather than losing
 * the deadline, which loses the error.
 */
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
    // Added here rather than at each call site so nothing can forget it. It is
    // a name somebody typed, not a credential -- see `lib/run/whoami`.
    const headers = { ...ownerHeaders(), ...(init.headers as Record<string, string>) };
    res = await fetch(`${base}${path}`, {
      ...init,
      headers,
      signal: deadline(options.signal, options.timeoutMs === undefined ? DEFAULT_TIMEOUT_MS : options.timeoutMs),
    });
  } catch (err) {
    // A deadline is a dead backend, not a cancellation, and it has to be told
    // apart from one: `AbortSignal.timeout` aborts with `TimeoutError` while a
    // caller's own abort is `AbortError`. Reported as offline because from the
    // reader's side "no answer" and "no connection" are the same problem.
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new ApiError(`백엔드(${base})가 응답하지 않습니다. 실행 중인지 확인하세요.`, 0);
    }
    // An abort is the caller getting what it asked for, not a failure. Wrapping
    // it would make React Query treat a cancelled query as a dead backend.
    if (err instanceof DOMException && err.name === "AbortError") throw err;
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

/**
 * A POST whose answer is a file rather than JSON.
 *
 * `request` parses every response as JSON, which a zip is not. The download it
 * produces cannot be a plain `<a href>` either: the route is a POST because the
 * selection travels in the body, so the bytes have to come back through fetch
 * and be handed to the browser as a Blob.
 *
 * Errors still arrive as JSON, so the failure path is the same as everywhere
 * else -- an `ApiError` carrying the server's Korean `detail`.
 */
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
      /* error bodies are not always JSON */
    }
    throw new ApiError(detail || `${res.status} ${res.statusText}`, res.status);
  }

  return {
    blob: await res.blob(),
    filename: filenameOf(res.headers.get("content-disposition")),
    headers: res.headers,
  };
}

/** The name the server chose for the file, if it said. */
function filenameOf(disposition: string | null): string | null {
  const found = disposition?.match(/filename="?([^";]+)"?/);
  return found ? found[1] : null;
}

/**
 * Hand a file to the browser.
 *
 * An object URL and a synthetic click, revoked on the next tick. Here rather
 * than in a component because two things download now -- a patch built in the
 * browser from returned text, and an archive streamed from the server -- and
 * the revoke is the part that gets forgotten.
 */
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

/**
 * The Korean sentence for a failure, chosen by what the server actually means.
 *
 * FastAPI's `detail` is written for whoever is reading the log, in English,
 * and several of these statuses mean something specific enough to be worth
 * saying properly.
 */
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
      // `require_model` answers 503, not 409, so the 409 branch above never
      // fired for it and its English sentence reached the reader raw inside a
      // Korean toast.
      if (/model/i.test(detail)) return "모델이 설정되지 않았습니다. 설정에서 엔드포인트를 확인하세요.";
      return detail;
    default:
      return detail;
  }
}
