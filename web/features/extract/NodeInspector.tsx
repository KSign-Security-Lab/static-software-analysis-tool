"use client";

import { Boxes } from "lucide-react";
import { EmptyState, PanelShell } from "@/components/workbench/PanelShell";
import { useCpgSource } from "../cpg/provider";

/**
 * What the extraction produced, in numbers.
 *
 * Not a per-node property sheet: the graph nodes already carry their label and
 * text, and a panel that repeats them adds a click without adding an answer.
 * What is not visible on the canvas is the shape of the whole thing.
 */
export default function NodeInspector() {
  const cpg = useCpgSource();
  const f2a = cpg.response?.f2a;

  if (!cpg.response) {
    return (
      <PanelShell title="추출 결과" note="노드를 누르면 속성이 여기에">
        <EmptyState icon={Boxes} title="아직 추출한 것이 없습니다">
          왼쪽 ‘소스’에서 코드를 고르고 ‘분석’을 누르면 그래프의 규모가, 노드를 누르면 그 노드의 속성이 여기에
          표시됩니다.
        </EmptyState>
      </PanelShell>
    );
  }

  const rows: [string, number | string][] = [
    ["메서드", cpg.response.method_count],
    ["핸들러 맵", f2a?.handler_maps?.length ?? 0],
    ["핸들러 해석", f2a?.handler_resolutions?.length ?? 0],
    ["필드 바인딩", f2a?.field_bindings?.length ?? 0],
    ["근거 패키지", f2a?.evidence_packages?.length ?? 0],
    ["후보 조각", f2a?.candidate_fragments?.length ?? 0],
  ];

  return (
    <PanelShell title="추출 결과" note={cpg.name}>
      <dl className="divide-y divide-line">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-2 px-2.5 py-1.5">
            <dt className="text-2xs text-ink-faint">{label}</dt>
            <dd className="font-mono text-xs text-ink">{value}</dd>
          </div>
        ))}
      </dl>

      {f2a?.limitations && f2a.limitations.length > 0 && (
        <section className="space-y-1 border-t border-line p-2.5">
          <h4 className="text-2xs font-semibold tracking-wide text-ink-faint uppercase">이 분석의 한계</h4>
          <ul className="space-y-1 text-2xs leading-relaxed text-ink-muted">
            {f2a.limitations.map((limitation, index) => (
              <li key={index}>{limitation}</li>
            ))}
          </ul>
        </section>
      )}
    </PanelShell>
  );
}
