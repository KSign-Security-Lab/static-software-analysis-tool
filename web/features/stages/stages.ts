export interface Stage {
  key: string;
  path: string;
  label: string;
  note: string;
  acceptsCpg: boolean;
  requiresCpg?: boolean;
}

export const STAGES: Stage[] = [
  { key: "cpg-jpype", path: "/cpg-jpype", label: "CPG", note: "소스 → GraphSON, 인프로세스 Joern", acceptsCpg: false },
  { key: "template", path: "/template", label: "Template", note: "CPG → 템플릿 노드", acceptsCpg: true },
  { key: "ast", path: "/ast", label: "AST", note: "CPG → 함수별 AST", acceptsCpg: true },
  { key: "dfg", path: "/dfg", label: "DFG", note: "CPG → 함수별 def-use DFG", acceptsCpg: true },
  { key: "analyze-functions", path: "/analyze-functions", label: "AST + DFG", note: "GNN 학습 스키마", acceptsCpg: true },
  { key: "f2a", path: "/f2a", label: "F2-A", note: "CPG → 근거 패키지", acceptsCpg: true, requiresCpg: true },
];

export function stageFor(key: string | null): Stage {
  return STAGES.find((each) => each.key === key) ?? STAGES[0];
}
