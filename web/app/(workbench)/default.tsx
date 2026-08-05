import { PanelShell, Placeholder } from "@/components/workbench/PanelShell";

/** The centre slot, when a soft navigation leaves it unmatched. */
export default function CentreDefault() {
  return (
    <PanelShell>
      <Placeholder what="화면을 고르세요." />
    </PanelShell>
  );
}
