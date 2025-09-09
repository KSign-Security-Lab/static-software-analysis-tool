import templateHandler from "@/src/handlers/TemplateHandler";
import { CPGRoot } from "@ssat/core/types/cpg";
import { TemplateNodes } from "@ssat/core/types/node";

class ASTHandler {
  private readonly baseUrl: string;

  constructor(baseUrl = "http://localhost:8000") {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  // Send a single function-level template AST to the Python server
  async getASTFromTemplate(templateAst: TemplateNodes) {
    const response = await fetch(`${this.baseUrl}/run`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ast: templateAst,
        options: {
          lift_pure_cond_calls: false,
        },
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`AST server error: ${response.status} - ${errorText}`);
    }

    const data = await response.json();
    return data;
  }

  // Convenience: derive Template from CPG, then get AST for the first function
  async getASTFromCPG(cpgData: CPGRoot) {
    const template = await templateHandler.generateTemplate(cpgData, {
      includeTextLines: false,
      includeFlattened: false,
    });

    const roots = template.templateResult;
    if (!roots || roots.length === 0) {
      throw new Error("No function templates generated from CPG data");
    }

    // For now, pick the first function root. Could be extended to choose by name.
    return this.getASTFromTemplate(roots[0]);
  }
}

const astHandler = new ASTHandler();
export default astHandler;
