"use client";

import { parseAsString, useQueryState } from "nuqs";

import { PanelShell } from "@/components/workbench/PanelShell";
import { cn } from "@/lib/utils";
import { STAGES } from "./stages";

export default function StageList() {
  const [stage, setStage] = useQueryState("stage", parseAsString.withDefault("cpg-jpype"));

  return (
    <PanelShell title="단계">
      <ul className="py-1">
        {STAGES.map((each) => (
          <li key={each.key}>
            <button
              type="button"
              onClick={() => void setStage(each.key)}
              className={cn(
                "w-full px-2.5 py-1.5 text-left transition-colors hover:bg-surface-2",
                stage === each.key && "bg-accent-wash",
              )}
            >
              <span className="block text-xs text-ink">{each.label}</span>
              <span className="block truncate text-2xs text-ink-faint">{each.note}</span>
            </button>
          </li>
        ))}
      </ul>
    </PanelShell>
  );
}
