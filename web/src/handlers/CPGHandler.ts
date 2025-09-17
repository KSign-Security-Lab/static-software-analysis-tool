// cpgHandler.ts
import { generateCpg as convertToCPG, CPGRoot } from "@ssat/core";

class CPGHandler {
  constructor() {
    // No external dependencies needed
  }

  /**
   * Generate CPG from raw C source string (pasted code).
   */
  async getCPGDataFromCSource(cSource: string): Promise<CPGRoot> {
    return await convertToCPG(cSource, "string");
  }

  /**
   * Generate CPG by writing C source to a temp .c file and using file mode.
   * Uses the provided original filename to preserve extension when possible.
   */
  async getCPGDataFromCFile(cSource: string, originalFilename?: string): Promise<CPGRoot> {
    const os = await import("os");
    const path = await import("path");
    const fs = await import("fs/promises");

    const tmpDir = os.tmpdir();
    const base = originalFilename && originalFilename.trim().length > 0 ? originalFilename : "input.c";
    const ensuredName = base.endsWith(".c") ? base : `${base}.c`;
    const tmpPath = path.join(tmpDir, `${Date.now()}_${Math.random().toString(36).slice(2)}_${ensuredName}`);

    try {
      await fs.writeFile(tmpPath, cSource, { encoding: "utf8" });
      // Prefer file mode to preserve filename semantics where supported
      try {
        return await convertToCPG(tmpPath, "file");
      } catch {
        // Fallback: if core cannot access file (e.g., ENOENT in nested temp), retry with string mode
        return await convertToCPG(cSource, "string");
      }
    } finally {
      // Best-effort cleanup
      try {
        await fs.unlink(tmpPath);
      } catch {
        // ignore
      }
    }
  }
}

const cpgHandler = new CPGHandler();
export default cpgHandler;
