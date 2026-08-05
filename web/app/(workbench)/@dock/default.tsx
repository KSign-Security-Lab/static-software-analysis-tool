import DockTabs from "@/components/workbench/DockTabs";
import { Placeholder } from "@/components/workbench/PanelShell";

export default function DockDefault() {
  return (
    <DockTabs
      scope="default"
      tabs={[
        { id: "problems", label: "문제", content: <Placeholder what="발견된 결과 목록이 여기 들어갑니다." /> },
        { id: "graph", label: "구조 지도", content: <Placeholder what="코드의 지식 그래프가 여기 들어갑니다." /> },
      ]}
    />
  );
}
