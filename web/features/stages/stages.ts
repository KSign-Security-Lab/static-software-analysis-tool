/**
 * The pipeline, one call at a time.
 *
 * The analyse page runs the whole chain and renders the result. This is the
 * other thing you want when a stage is misbehaving: call it alone and read the
 * JSON it actually returned.
 */
export interface Stage {
  key: string;
  path: string;
  label: string;
  note: string;
  /** Whether the endpoint takes a prebuilt CPG instead of source. */
  acceptsCpg: boolean;
  /** Whether it takes *only* a CPG. */
  requiresCpg?: boolean;
}

export const STAGES: Stage[] = [
  { key: "cpg-jpype", path: "/cpg-jpype", label: "CPG (jpype)", note: "소스 → GraphSON, 인프로세스 Joern", acceptsCpg: false },
  { key: "cpg-docker", path: "/cpg-docker", label: "CPG (docker)", note: "소스 → GraphSON, Joern 컨테이너", acceptsCpg: false },
  { key: "template", path: "/template", label: "Template", note: "CPG → 템플릿 노드", acceptsCpg: true },
  { key: "ast", path: "/ast", label: "AST", note: "CPG → 함수별 AST", acceptsCpg: true },
  { key: "dfg", path: "/dfg", label: "DFG", note: "CPG → 함수별 def-use DFG", acceptsCpg: true },
  { key: "analyze-functions", path: "/analyze-functions", label: "AST + DFG", note: "GNN 학습 스키마", acceptsCpg: true },
  { key: "f2a", path: "/f2a", label: "F2-A", note: "CPG → 근거 패키지", acceptsCpg: true, requiresCpg: true },
];

export function stageFor(key: string | null): Stage {
  return STAGES.find((each) => each.key === key) ?? STAGES[0];
}
