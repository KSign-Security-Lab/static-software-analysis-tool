import { InputType, type PipelineData } from "./types";

export const pipelineOptions: PipelineData = {
  stages: [
    {
      id: "cpg",
      name: "CPG Generation",
      description: "Generate Code Property Graph from C source code",
      requires: ["joern-server"],
      inputs: [InputType.CSource],
      outputs: ["cpg-data"],
      apiEndpoint: "/api/cpg",
    },
    {
      id: "dfg",
      name: "DFG Generation",
      description: "Generate Data Flow Graph from CPG data",
      requires: ["cpg-data"],
      inputs: [InputType.CSource, InputType.CpgData],
      outputs: ["dfg-data"],
      apiEndpoint: "/api/dfg",
    },
    {
      id: "template",
      name: "Template Generation",
      description: "Generate Template artifacts from CPG data",
      requires: ["cpg-data"],
      inputs: [InputType.CSource, InputType.CpgData],
      outputs: ["template-data"],
      apiEndpoint: "/api/template",
    },
    {
      id: "ast",
      name: "AST Generation",
      description: "Generate Abstract Syntax Tree using Template-derived function AST",
      requires: ["template-data", "ast-server"],
      inputs: [InputType.CSource, InputType.CpgData, InputType.TemplateData],
      outputs: ["ast-data"],
      apiEndpoint: "/api/ast",
    },
  ],
  dependencies: {
    cpg: [],
    dfg: ["cpg"],
    template: ["cpg"],
    ast: ["template"],
  },
  serverRequirements: {
    "joern-server": {
      name: "Joern Server",
      port: 8080,
      description: "Required for CPG generation",
    },
    "ast-server": {
      name: "AST Server",
      port: 8000,
      description: "Required for AST generation",
    },
  },
};
