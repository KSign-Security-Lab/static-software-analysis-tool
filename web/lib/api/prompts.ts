import { get, type RequestOptions } from "./client";
import type { PromptRow } from "./types";

export function fetchPrompts(options?: RequestOptions): Promise<{ prompts: PromptRow[] }> {
  return get<{ prompts: PromptRow[] }>("/agent/prompts", options);
}
