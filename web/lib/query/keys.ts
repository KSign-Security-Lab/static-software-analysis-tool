/**
 * Query keys, in one place.
 *
 * Hierarchical and run-scoped, so a whole run's cache is one call to
 * `invalidateQueries({ queryKey: keys.run(id) })` -- which matters because the
 * event stream invalidates by prefix and the alternative is listing every
 * dependent key at each call site and forgetting one.
 */
export const keys = {
  agent: ["agent"] as const,

  health: (probe: boolean) => ["agent", "health", { probe }] as const,
  /** The graph's shape, not a run's. Changes when the server restarts. */
  graph: () => ["agent", "graph"] as const,
  prompts: () => ["agent", "prompts"] as const,
  runs: () => ["agent", "runs"] as const,

  run: (id: string) => ["agent", "run", id] as const,
  summary: (id: string) => ["agent", "run", id, "summary"] as const,
  files: (id: string) => ["agent", "run", id, "files"] as const,
  file: (id: string, path: string) => ["agent", "run", id, "file", path] as const,
  findings: (id: string) => ["agent", "run", id, "findings"] as const,
  spans: (id: string) => ["agent", "run", id, "spans"] as const,
  threads: (id: string) => ["agent", "run", id, "threads"] as const,
  knowledge: (id: string) => ["agent", "run", id, "knowledge"] as const,

  /** The structural line: Joern is expensive, so results are keyed by input. */
  analyze: (hash: string) => ["ssat", "analyze", hash] as const,
} as const;

/** Everything a finding's 판단 과정 reads; what a finished node invalidates. */
export function recordedKeys(id: string) {
  return [keys.spans(id), keys.threads(id)];
}
