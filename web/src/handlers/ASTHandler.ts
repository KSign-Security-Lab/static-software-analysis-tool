import { generateAst as convertToAST, generateTemplate as convertToTemplate, type CPGRoot, type TemplateNodes, IASTResult } from "@ssat/core";

class ASTHandler {
  constructor() {
    // No external dependencies needed - uses clean conversion functions
  }

  // Send a single function-level template AST to the Python server
  async getASTFromTemplate(templateAst: TemplateNodes[]): Promise<IASTResult[]> {
    const result = await convertToAST(templateAst);

    return result;
  }

  // Convenience: derive Template from CPG, then get AST for the first function
  async getASTFromCPG(cpgData: CPGRoot): Promise<IASTResult[]> {
    const template = await convertToTemplate(cpgData);

    const roots = template;
    if (!roots || roots.length === 0) {
      throw new Error("No function templates generated from CPG data");
    }

    // For now, pick the first function root. Could be extended to choose by name.
    return this.getASTFromTemplate(roots);
  }
}

const astHandler = new ASTHandler();
export default astHandler;
