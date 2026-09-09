import { get, post } from "@/lib/http";
import type { AnalyzeResponse, F2AResult, PipelineResponse } from "@/lib/types";

export interface AnalyzeInput {
  source: string;
  language: string;
  filename?: string;
}

export function analyze(input: AnalyzeInput): Promise<AnalyzeResponse> {
  return post<AnalyzeResponse>("/analyze", input);
}

export function f2aFromCpg(cpg: unknown): Promise<F2AResult> {
  return post<F2AResult>("/f2a", { cpg });
}

export function analyzeFunctions(cpg: unknown): Promise<PipelineResponse> {
  return post<PipelineResponse>("/analyze-functions", { cpg });
}

export function health(): Promise<{ status: string; backends: Record<string, boolean> }> {
  return get("/health");
}
