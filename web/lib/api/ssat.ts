import { get, post } from "@/lib/http";
import type { AnalyzeResponse, F2AResult, PipelineResponse } from "@/lib/types";

/** The structural line: Joern CPG, the SSAT pipeline, and F2-A. */

export interface AnalyzeInput {
  source: string;
  language: string;
  filename?: string;
}

/** Compile source and run F2-A in one call. */
export function analyze(input: AnalyzeInput): Promise<AnalyzeResponse> {
  return post<AnalyzeResponse>("/analyze", input);
}

/** F2-A over a CPG that already exists, so Joern does not run again. */
export function f2aFromCpg(cpg: unknown): Promise<F2AResult> {
  return post<F2AResult>("/f2a", { cpg });
}

/**
 * Per-function AST + def-use DFG from the SSAT pipeline.
 *
 * A different thing from the AST/DFG *views* the browser projects out of a CPG
 * by edge label -- these are the extractor's own statement-level artifacts.
 */
export function analyzeFunctions(cpg: unknown): Promise<PipelineResponse> {
  return post<PipelineResponse>("/analyze-functions", { cpg });
}

export function health(): Promise<{ status: string; backends: Record<string, boolean> }> {
  return get("/health");
}
