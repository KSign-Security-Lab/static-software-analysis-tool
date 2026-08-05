import { PanelShell, Placeholder } from "@/components/workbench/PanelShell";

export default function InspectorDefault() {
  return (
    <PanelShell title="인스펙터">
      <Placeholder what="선택한 결과나 호출의 상세가 여기 들어갑니다." />
    </PanelShell>
  );
}
