// dfgHandler.ts
import { validateCPGRoot } from "@ssat/core/cpg/validate/zod";
import { DFGBuilder } from "@ssat/core/dfg/DFGBuilder";
import DFGSync from "@ssat/core/dfg/DFGSync";
import { CPGRoot } from "@ssat/core/types/cpg";
import { IDFGGraph } from "@ssat/core/types/dfg";
import { TemplateFlattenedGraph } from "@ssat/core/types/node";

type GenerateDFGOptions = {
  /**
   * Optional AST data for DFG synchronization.
   * If provided, the DFG will be synchronized with the AST.
   */
  astData?: TemplateFlattenedGraph;
  /**
   * If true, validate the input CPG data before processing.
   * Defaults to true.
   */
  validateInput?: boolean;
};

class DFGHandler {
  constructor() {
    // No external dependencies needed
  }

  // ---------- Validation helpers ----------

  private validateCPG(root: CPGRoot): void {
    try {
      validateCPGRoot([root.export]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(`CPG validation failed: ${msg}`);
    }
  }

  // ---------- Public API ----------

  /**
   * Generate a DFG (Data Flow Graph) from CPG data.
   *
   * Steps:
   * 1) Validate the input CPG data (optional)
   * 2) Build the raw DFG using DFGBuilder
   * 3) Optionally synchronize with AST data using DFGSync
   * 4) Return the processed DFG data
   */
  async generateDFG(cpgData: CPGRoot, opts: GenerateDFGOptions = {}): Promise<IDFGGraph> {
    const { validateInput = true, astData } = opts;

    // Validate input if requested
    if (validateInput) {
      this.validateCPG(cpgData);
    }

    // Build the raw DFG
    const dfgBuilder = new DFGBuilder(cpgData);
    const rawDFG = dfgBuilder.build();

    // If AST data is provided, synchronize the DFG with it
    if (astData) {
      const dfgSync = new DFGSync(rawDFG, astData);
      return dfgSync.sync();
    }

    return rawDFG;
  }

  /**
   * Generate DFG from a JSON string containing CPG data.
   */
  async generateDFGFromString(cpgJsonString: string, opts: GenerateDFGOptions = {}): Promise<IDFGGraph> {
    let cpgData: CPGRoot;
    try {
      cpgData = JSON.parse(cpgJsonString) as CPGRoot;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(`Failed to parse CPG JSON: ${msg}`);
    }

    return this.generateDFG(cpgData, opts);
  }
}

const dfgHandler = new DFGHandler();
export default dfgHandler;
