import { NextResponse } from "next/server";

export async function GET() {
  const pipelineOptions = {
    stages: [
      {
        id: "cpg",
        name: "CPG Generation",
        description: "Generate Code Property Graph from C source code",
        requires: ["joern-server"],
        inputs: ["c-source"],
        outputs: ["cpg-data"],
        apiEndpoint: "/api/cpg",
      },
      {
        id: "dfg",
        name: "DFG Generation",
        description: "Generate Data Flow Graph from CPG data",
        requires: ["cpg-data"],
        inputs: ["c-source", "cpg-data"],
        outputs: ["dfg-data"],
        apiEndpoint: "/api/dfg",
      },
      {
        id: "template",
        name: "Template Generation",
        description: "Generate Template artifacts from CPG data",
        requires: ["cpg-data"],
        inputs: ["c-source", "cpg-data"],
        outputs: ["template-data"],
        apiEndpoint: "/api/template",
      },
      {
        id: "ast",
        name: "AST Generation",
        description: "Generate Abstract Syntax Tree using Template-derived function AST",
        requires: ["template-data", "ast-server"],
        inputs: ["c-source", "cpg-data", "template-data"],
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

  return NextResponse.json({
    status: 200,
    ok: true,
    message: "Pipeline options retrieved successfully.",
    data: pipelineOptions,
  });
}
