export enum InputType {
  CSource = "c-source",
  CpgData = "cpg-data",
  TemplateData = "template-data",
}

export type PipelineStage = {
  id: string;
  name: string;
  description: string;
  requires: string[];
  inputs: InputType[];
  outputs: string[];
  apiEndpoint: string;
};

export type PipelineData = {
  stages: PipelineStage[];
  dependencies: Record<string, string[]>;
  serverRequirements: Record<string, { name: string; port: number; description: string }>;
};
