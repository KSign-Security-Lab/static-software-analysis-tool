import { del, get, put, seg, type RequestOptions } from "./client";
import type { PromptRow } from "./types";

/**
 * Prompt overrides.
 *
 * Every mutation returns the whole list, so nothing here needs a refetch --
 * the caller writes the response straight into the cache.
 *
 * Names contain a colon (`lens:memory`), which is why the path segment is
 * escaped.
 */

export function fetchPrompts(options?: RequestOptions): Promise<{ prompts: PromptRow[] }> {
  return get<{ prompts: PromptRow[] }>("/agent/prompts", options);
}

export function savePrompt(name: string, text: string): Promise<{ prompts: PromptRow[] }> {
  return put<{ prompts: PromptRow[] }>(`/agent/prompts/${seg(name)}`, { text });
}

export function resetPrompt(name: string): Promise<{ prompts: PromptRow[] }> {
  return del<{ prompts: PromptRow[] }>(`/agent/prompts/${seg(name)}`);
}
