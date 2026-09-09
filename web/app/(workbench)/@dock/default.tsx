import { PanelBottom } from "lucide-react";

import DockTabs from "@/components/workbench/DockTabs";
import { EmptyState } from "@/components/workbench/PanelShell";

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
