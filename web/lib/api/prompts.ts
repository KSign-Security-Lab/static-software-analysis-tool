import { get, type RequestOptions } from "./client";
import type { PromptRow } from "./types";

/**
 * The system prompts a run used, read-only.
 *
 * Adopting a tuned prompt from the browser was the studio's. Tuning happens
 * through `agent.tuner` now, which replays a recorded run before it proposes a
 * change -- something a PUT from a page could not do. What this is still for is
 * naming the prompt behind a recorded call in a finding's 판단 과정.
 */
export function fetchPrompts(options?: RequestOptions): Promise<{ prompts: PromptRow[] }> {
  return get<{ prompts: PromptRow[] }>("/agent/prompts", options);
}
