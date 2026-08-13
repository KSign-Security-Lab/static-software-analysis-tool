/**
 * The run as a person would describe it.
 *
 * The graph has fourteen nodes and that is the right number for a graph: `skip`
 * and `locate` are real, and leaving them out would make the drawing lie. It is
 * the wrong number for a strip that has to be read at a glance while a run is
 * moving, so the nodes are grouped into the seven phases somebody would name if
 * you asked them what the checker does.
 *
 * Every node belongs to exactly one stage. That is enforced by a test against
 * the node list the server reports, so adding a node to the pipeline and
 * forgetting it here fails loudly rather than leaving a stage that never lights.
 */
/**
 * The specialists, as `agent/schema.py`'s `Lens` names them.
 *
 * Written out rather than derived from a run, because the strip has to show the
 * shape of the pipeline before anything has run. The test below checks this
 * against the node list the server reports, so a sixth specialist cannot be
 * added on that side and go missing here.
 */
const LENS_NODES = ["memory", "injection", "access", "crypto", "logic"] as const;

export interface Stage {
  id: string;
  label: string;
  /** What it is for, one line, for the tooltip. */
  hint: string;
  nodes: readonly string[];
}

export const STAGES: readonly Stage[] = [
  { id: "plan", label: "계획", hint: "어떤 단위를 어떤 순서로 읽을지 정합니다", nodes: ["plan", "context"] },
  { id: "triage", label: "선별", hint: "전문가의 시간을 들일 단위인지 값싸게 거릅니다", nodes: ["triage", "skip"] },
  { id: "scout", label: "범위", hint: "큰 단위를 자세히 볼 구간으로 좁힙니다", nodes: ["scout"] },
  { id: "lens", label: "전문가", hint: "배정된 전문가가 각자의 관점으로 읽습니다", nodes: LENS_NODES },
  { id: "gather", label: "근거", hint: "제기된 주장을 도구로 확인합니다", nodes: ["locate", "gather"] },
  { id: "verify", label: "판정", hint: "주장을 반박해 보고 살아남는지 봅니다", nodes: ["verify"] },
  { id: "reduce", label: "정리", hint: "살아남은 것을 보고서에 씁니다", nodes: ["reduce"] },
];

export type StageState = "waiting" | "running" | "done";

/**
 * Where the run is.
 *
 * `running` is the node names the stream reports in flight, which is the only
 * live signal there is; everything else is inferred from it and from the phase.
 * A stage is done when the run has moved past it -- meaning something later is
 * running, or the run has finished -- rather than by counting, because a wave
 * revisits earlier stages and a counter would tick backwards.
 */
export function stageStates(
  running: readonly string[],
  phase: "idle" | "starting" | "running" | "paused" | "finished" | "failed",
  /**
   * Calls each stage has made, when they are known.
   *
   * A run that finished before this page was opened has no stream to report it:
   * the phase is `idle` and nothing is in flight, so every stage read as waiting
   * under a report full of its results. A stage that made calls has run,
   * whatever the stream is currently saying.
   */
  calls: Record<string, number> = {},
): Record<string, StageState> {
  const active = new Set(running);
  const busy = STAGES.map((stage) => stage.nodes.some((node) => active.has(node)));
  const furthest = busy.lastIndexOf(true);

  const worked = STAGES.map((stage) => (calls[stage.id] ?? 0) > 0).lastIndexOf(true);
  const states: Record<string, StageState> = {};
  STAGES.forEach((stage, at) => {
    if (phase === "finished") states[stage.id] = "done";
    else if (busy[at]) states[stage.id] = "running";
    else if (furthest > at) states[stage.id] = "done";
    // Everything up to the last stage that made a call. `계획` and `정리` are
    // code, not model calls, so they have no count of their own to go by -- but
    // a run that reached 판정 plainly got through planning.
    else if (furthest === -1 && at <= worked) states[stage.id] = "done";
    else states[stage.id] = "waiting";
  });
  return states;
}

/** How many model calls a stage made, out of the per-node counts the server reports. */
export function stageCalls(notes: readonly { node: string; calls: number }[]): Record<string, number> {
  const byNode = new Map(notes.map((note) => [note.node, note.calls]));
  const counts: Record<string, number> = {};
  for (const stage of STAGES) {
    counts[stage.id] = stage.nodes.reduce((sum, node) => sum + (byNode.get(node) ?? 0), 0);
  }
  return counts;
}
