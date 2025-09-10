import templateHandler from "@/src/handlers/TemplateHandler";
import { CPGRoot } from "@ssat/core/types/cpg";
import { TemplateNodes } from "@ssat/core/types/node";

class ASTHandler {
  private readonly baseUrl: string;

  constructor(baseUrl?: string) {
    const envUrl = process.env.AST_SERVER_URL || process.env.NEXT_PUBLIC_AST_SERVER_URL || "http://localhost:8000";
    const resolved = (baseUrl ?? envUrl).replace(/\/+$/, "");
    this.baseUrl = resolved;
  }

  // Send a single function-level template AST to the Python server
  async getASTFromTemplate(templateAst: TemplateNodes) {
    try {
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
        throw new Error(`AST server error (${this.baseUrl}/run): ${response.status} - ${errorText}`);
      }

      const data = await response.json();
      return data;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      // Normalize common network error message
      if (msg.toLowerCase().includes("fetch failed")) {
        throw new Error(`Failed to reach AST server at ${this.baseUrl}/run. Ensure it is running and reachable. Original: ${msg}`);
      }
      throw new Error(msg);
    }
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
