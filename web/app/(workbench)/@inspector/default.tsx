import { PanelRight } from "lucide-react";

import { EmptyState, PanelShell } from "@/components/workbench/PanelShell";

/** For surfaces with no inspector of their own: 스테이지, which starts collapsed. */
export default function InspectorDefault() {
  return (
    <PanelShell title="인스펙터">
      <EmptyState icon={PanelRight} title="이 화면에는 인스펙터가 없습니다">
        ⌘⌥B 로 이 칸을 다시 접을 수 있습니다.
      </EmptyState>
    </PanelShell>
  );
}
