import { generateDfg as convertToDFG, type CPGRoot, type IASTResult, IDFGGraph, generateAst, generateTemplate } from "@ssat/core";

class DFGHandler {
  constructor() {
    // No external dependencies needed
  }

  // ---------- Public API ----------

  /**
   * Generate a DFG (Data Flow Graph) from CPG data.
   * Uses the clean conversion function from core package.
   */
  generateDFG(cpgData: CPGRoot, astInput?: IASTResult[]): IDFGGraph {
    if (!astInput) {
      const template = generateTemplate(cpgData);
      const ast = generateAst(template);
      astInput = ast;
    }

    const result = convertToDFG(cpgData, astInput);

    return result[0];
  }

  /**
   * Generate DFG from a JSON string containing CPG data.
   */
  generateDFGFromString(cpgJsonString: string, astData?: IASTResult[]): IDFGGraph {
    let cpgData: CPGRoot;
    try {
      cpgData = JSON.parse(cpgJsonString) as CPGRoot;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(`Failed to parse CPG JSON: ${msg}`);
    }

    return this.generateDFG(cpgData, astData);
  }
}

const dfgHandler = new DFGHandler();
export default dfgHandler;
