"use client";

import dynamic from "next/dynamic";
import { parseAsString, useQueryState } from "nuqs";
import { useMemo, useState } from "react";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { PanelShell } from "@/components/workbench/PanelShell";
import { parseCpg } from "@/lib/cpg";
import { contract, internalMethods, isNoise, scopeCallGraph, scopeToMethod } from "@/lib/graphops";
import { nonEmptyFunctions, pipelineAstView, pipelineDfgView } from "@/lib/pipeline";
import { CPG_VIEW_KEYS, PIPELINE_VIEW_KEYS, type ViewKey } from "@/lib/types";
import { buildViews } from "@/lib/views";
import { useCpgSource } from "../cpg/provider";
import { usePipeline } from "./queries";

const CpgCanvas = dynamic(() => import("./CpgCanvas"), {
  ssr: false,
  loading: () => (
    <div className="grid h-full place-items-center p-4">
      <Skeleton className="h-20 w-1/2" />
    </div>
  ),
});

const LABEL: Record<ViewKey, string> = {
  ast: "AST",
  cfg: "CFG",
  dfg: "DFG",
  cg: "CG",
  cpg: "CPG",
  "pipeline-ast": "AST (파이프라인)",
  "pipeline-dfg": "DFG (파이프라인)",
};

/**
 * What the front end actually built out of the source.
 *
 * Two vocabularies that both say "AST" and "DFG", so the picker groups them
 * apart. The CPG views are Joern's own graph projected by edge label; the
 * pipeline views are the SSAT extractor's statement-level output. Reading one
 * as the other is the mistake this grouping exists to prevent.
 */
export default function ExtractPane() {
  const cpg = useCpgSource();
  const [view, setView] = useQueryState("view", parseAsString.withDefault("ast").withOptions({ history: "replace" }));
  const [method, setMethod] = useState<string>("all");
  const [simplify, setSimplify] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  const parsed = useMemo(() => (cpg.response ? parseCpg(cpg.response.cpg) : null), [cpg.response]);
  const pipeline = usePipeline(cpg.response?.cpg ?? null);

  const methods = useMemo(() => (parsed ? internalMethods(parsed) : []), [parsed]);
  const functions = useMemo(() => nonEmptyFunctions(pipeline.data?.functions ?? []), [pipeline.data]);

  const key = view as ViewKey;
  const isPipeline = PIPELINE_VIEW_KEYS.includes(key as (typeof PIPELINE_VIEW_KEYS)[number]);

  const graph = useMemo(() => {
    if (isPipeline) {
      const fn = functions.find((each) => each.function_name === method) ?? functions[0];
      if (!fn) return null;
      return key === "pipeline-ast" ? pipelineAstView(fn) : pipelineDfgView(fn);
    }
    if (!parsed) return null;

    let built = buildViews(parsed)[key as (typeof CPG_VIEW_KEYS)[number]];
    if (method !== "all") {
      built = key === "cg" ? scopeCallGraph(built, method) : scopeToMethod(built, parsed, method);
    }
    // Folding operators, literals and blocks is what keeps a real CPG legible;
    // the reducers reconnect the edges across whatever they remove.
    if (simplify) built = contract(built, (node) => !isNoise(node));
    return built;
  }, [isPipeline, functions, method, parsed, key, simplify]);

  const picker = isPipeline ? functions.map((f) => f.function_name) : methods.map((m) => m.name);

  return (
    <PanelShell
      title="그래프"
      note={graph ? `노드 ${graph.nodes.length} · 엣지 ${graph.edges.length}` : undefined}
      actions={
        <>
          <Select value={view} onValueChange={(next) => void setView(next)}>
            <SelectTrigger size="sm" className="h-7 w-44 text-2xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CPG_VIEW_KEYS.map((each) => (
                <SelectItem key={each} value={each}>
                  {LABEL[each]}
                </SelectItem>
              ))}
              {PIPELINE_VIEW_KEYS.map((each) => (
                <SelectItem key={each} value={each}>
                  {LABEL[each]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {picker.length > 0 && (
            <Select value={method} onValueChange={setMethod}>
              <SelectTrigger size="sm" className="h-7 w-40 text-2xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {!isPipeline && <SelectItem value="all">전체 메서드</SelectItem>}
                {picker.map((name) => (
                  <SelectItem key={name} value={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          {!isPipeline && (
            <span className="flex items-center gap-1.5">
              <Switch id="simplify" checked={simplify} onCheckedChange={setSimplify} />
              <Label htmlFor="simplify" className="text-2xs text-ink-muted">
                단순화
              </Label>
            </span>
          )}
        </>
      }
      bodyClassName="overflow-hidden"
    >
      {!cpg.response ? (
        <div className="grid h-full place-items-center p-6 text-center">
          <p className="max-w-72 text-sm text-ink-faint">‘분석’을 눌러 CPG를 만들면 그래프가 여기 표시됩니다.</p>
        </div>
      ) : isPipeline && pipeline.isPending ? (
        <div className="grid h-full place-items-center p-4">
          <p className="text-xs text-ink-faint">파이프라인 산출물을 불러오는 중…</p>
        </div>
      ) : graph ? (
        <CpgCanvas view={graph} selected={selected} onSelect={setSelected} />
      ) : (
        <p className="p-4 text-xs text-ink-faint">이 뷰에 표시할 노드가 없습니다.</p>
      )}
    </PanelShell>
  );
}
