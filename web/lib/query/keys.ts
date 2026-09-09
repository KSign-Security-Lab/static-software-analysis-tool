export const keys = {
  agent: ["agent"] as const,

  health: (probe: boolean) => ["agent", "health", { probe }] as const,
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

  analyze: (hash: string) => ["ssat", "analyze", hash] as const,
} as const;

export function recordedKeys(id: string) {
  return [keys.spans(id), keys.threads(id)];
}
