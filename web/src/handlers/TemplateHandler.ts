// templateHandler.ts
import { generateTemplate as convertToTemplate, type CPGRoot, TemplateNodes } from "@ssat/core";

class TemplateHandler {
  constructor() {
    // No external dependencies needed
  }

  // ---------- Public API ----------

  /**
   * Generate template artifacts from CPG data.
   * Uses the clean conversion function from core package.
   */
  async generateTemplate(cpgData: CPGRoot): Promise<TemplateNodes[]> {
    return convertToTemplate(cpgData);
  }

  /**
   * Generate template from a JSON string containing CPG data.
   */
  async generateTemplateFromString(cpgJsonString: string): Promise<TemplateNodes[]> {
    let cpgData: CPGRoot;
    try {
      cpgData = JSON.parse(cpgJsonString) as CPGRoot;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(`Failed to parse CPG JSON: ${msg}`);
    }

    return this.generateTemplate(cpgData);
  }
}

const templateHandler = new TemplateHandler();
export default templateHandler;
