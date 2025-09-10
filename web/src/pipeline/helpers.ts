import type { InputType, PipelineData, PipelineStage } from "./types";

export function filterStagesForInput(pipeline: PipelineData, input: InputType): PipelineStage[] {
  return pipeline.stages.filter((stage) => {
    if (input === "c-source") return true;
    return stage.inputs.includes(input);
  });
}

export function defaultStageForInput(pipeline: PipelineData, input: InputType): string | undefined {
  const available = filterStagesForInput(pipeline, input);
  return available[0]?.id;
}

export function findStage(pipeline: PipelineData | null, id: string): PipelineStage | undefined {
  if (!pipeline) return undefined;
  return pipeline.stages.find((s) => s.id === id);
}

