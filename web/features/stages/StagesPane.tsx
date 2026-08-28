"use client";

import { useMutation } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { parseAsBoolean, parseAsString, useQueryState } from "nuqs";
import { useState } from "react";

import CodeEditor from "@/components/editor/CodeEditor.lazy";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { PanelShell } from "@/components/workbench/PanelShell";
import { describeError, post } from "@/lib/api/client";
import { useCpgSource } from "../cpg/provider";
import { stageFor } from "./stages";

/**
 * One stage, called alone, with whatever it returned.
 *
 * Request and response in the same panel rather than split across slots: this
 * is a debug tool for the moment a stage misbehaves, and the two halves are
 * read together. Deliberately raw output -- a rendering that interprets it is
 * exactly what you do not want when you are checking what it actually said.
 */
export default function StagesPane() {
  const cpg = useCpgSource();
  const [stageKey] = useQueryState("stage", parseAsString.withDefault("cpg-jpype"));
  const [useCpg, setUseCpg] = useQueryState("cpg", parseAsBoolean.withDefault(false));
  const [cpgText, setCpgText] = useState("");

  const stage = stageFor(stageKey);
  const cpgMode = stage.requiresCpg || (useCpg && stage.acceptsCpg);

  const run = useMutation({
    mutationFn: async () => {
      const started = performance.now();
      const body = cpgMode
        ? { cpg: JSON.parse(cpgText || JSON.stringify(cpg.response?.cpg ?? {})) }
        : { source: cpg.text, language: cpg.language, filename: cpg.name };
      const result = await post<unknown>(stage.path, body);
      return { result, ms: Math.round(performance.now() - started) };
    },
  });

  return (
    <PanelShell
      title={`${stage.label} · ${cpgMode ? "CPG JSON" : "소스"}`}
      note={stage.note}
      actions={
        <>
          {stage.acceptsCpg && !stage.requiresCpg && (
            <span className="flex items-center gap-1.5">
              <Switch id="use-cpg" checked={useCpg} onCheckedChange={(next) => void setUseCpg(next)} />
              <Label htmlFor="use-cpg" className="text-2xs text-ink-muted">
                CPG 입력
              </Label>
            </span>
          )}
          <Button size="xs" onClick={() => run.mutate()} disabled={run.isPending}>
            <Play />
            {run.isPending ? "실행 중…" : "실행"}
          </Button>
        </>
      }
      bodyClassName="overflow-hidden"
    >
      <div className="grid h-full grid-rows-2">
        <div className="min-h-0 border-b border-line">
          {cpgMode ? (
            <CodeEditor
              path="request.json"
              language="json"
              value={cpgText || JSON.stringify(cpg.response?.cpg ?? {}, null, 2)}
              onChange={setCpgText}
            />
          ) : (
            <CodeEditor path={cpg.name} language={cpg.language} value={cpg.text} onChange={cpg.setText} />
          )}
        </div>

        <section className="flex min-h-0 flex-col">
          <header className="flex h-7 shrink-0 items-center gap-2 border-b border-line px-2.5 text-2xs">
            <span className="font-semibold tracking-wide text-ink-muted uppercase">응답</span>
            {run.isSuccess && <span className="font-mono text-ink-faint">{run.data.ms}ms</span>}
            <code className="ml-auto font-mono text-ink-faint">POST {stage.path}</code>
          </header>
          <div className="min-h-0 flex-1 overflow-auto">
            {run.isError ? (
              <p className="p-3 text-2xs whitespace-pre-wrap text-danger">{describeError(run.error)}</p>
            ) : run.isSuccess ? (
              <pre className="p-3 font-mono text-2xs leading-relaxed text-ink-muted">
                {JSON.stringify(run.data.result, null, 2)}
              </pre>
            ) : (
              <p className="p-3 text-2xs text-ink-faint">‘실행’을 누르면 이 단계의 원본 응답이 여기 표시됩니다.</p>
            )}
          </div>
        </section>
      </div>
    </PanelShell>
  );
}
