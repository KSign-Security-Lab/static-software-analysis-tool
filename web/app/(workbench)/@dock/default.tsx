import { PanelBottom } from "lucide-react";

import DockTabs from "@/components/workbench/DockTabs";
import { EmptyState } from "@/components/workbench/PanelShell";

/**
 * For surfaces with no bottom panel of their own: 추출 and 스테이지.
 *
 * It used to render two staging placeholders reading 준비 중, one of them a
 * "문제" tab on screens that do not look for problems. Both surfaces start
 * with this pane collapsed now (see layout-cookie.ts), so this is what is
 * behind ⌘J rather than what anyone is shown.
 */
export default function DockDefault() {
  return (
    <DockTabs
      tabs={[
        {
          id: "none",
          label: "아래 패널",
          content: (
            <EmptyState icon={PanelBottom} title="이 화면에는 아래 패널이 없습니다">
              ⌘J 로 이 칸을 다시 접을 수 있습니다.
            </EmptyState>
          ),
        },
      ]}
    />
  );
}
