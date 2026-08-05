import { PanelShell, Placeholder } from "@/components/workbench/PanelShell";

/**
 * The explorer, for every perspective that has not overridden it.
 *
 * A parallel-route slot needs a `default.tsx` at every level or a soft
 * navigation leaves it showing whatever it rendered last, and a hard one 404s.
 */
export default function SideDefault() {
  return (
    <PanelShell title="탐색기">
      <Placeholder what="실행의 파일 트리가 여기 들어갑니다." />
    </PanelShell>
  );
}
