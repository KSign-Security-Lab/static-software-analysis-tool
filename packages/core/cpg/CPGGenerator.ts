import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { promises as fs } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import { CPGRoot, ICPGRootExport } from "../types/cpg";

export interface StandaloneCPGResult {
  cpgData: CPGRoot;
  projectName: string;
  methodCount: number;
}

export class CPGGenerator {
  public async convertToCPGStandalone(cSource: string, options: { filename?: string } = {}): Promise<StandaloneCPGResult> {
    const filename = options.filename ?? "main.c";

    if (!filename.endsWith(".c")) {
      throw new Error(`filename must end with ".c": received "${filename}"`);
    }

    // Create temporary directory
    const tmpDir = path.join(os.tmpdir(), `joern-cpg-${randomUUID()}`);
    await fs.mkdir(tmpDir, { recursive: true });

    try {
      // Write C source to temporary file
      const sourceFile = path.join(tmpDir, filename);
      const content = cSource.endsWith("\n") ? cSource : `${cSource}\n`;
      await fs.writeFile(sourceFile, content, "utf8");

      // Generate CPG using joern-parse and joern-export
      const cpgExport = await this.generateCPGFromFile(sourceFile);

      // Generate project name
      const projectName = `c-src-${randomUUID().slice(0, 8)}`;

      // Count methods for validation
      const methodCount = this.countMethods({ export: cpgExport } as CPGRoot);

      return {
        cpgData: { export: cpgExport } as CPGRoot,
        projectName,
        methodCount,
      };
    } finally {
      // Clean up temporary directory
      try {
        await fs.rm(tmpDir, { recursive: true, force: true });
      } catch {
        // Ignore cleanup errors
      }
    }
  }

  private async generateCPGFromFile(sourceFile: string): Promise<ICPGRootExport> {
    const tmpDir = path.dirname(sourceFile);

    // Step 1: joern-parse
    const parseResult = await new Promise<{ error?: string; success: boolean }>((resolve) => {
      const parse = spawn("joern-parse", [sourceFile], { cwd: tmpDir });
      let stderr = "";

      parse.stderr.on("data", (data: Buffer) => {
        stderr += data.toString();
      });

      parse.on("close", (code) => {
        if (code === 0) {
          resolve({ success: true });
        } else {
          resolve({ success: false, error: stderr || `joern-parse exited with code ${String(code)}` });
        }
      });
    });

    if (!parseResult.success) {
      throw new Error(`joern-parse failed: ${String(parseResult.error)}`);
    }

    // Check if cpg.bin was created
    const cpgPath = path.join(tmpDir, "cpg.bin");
    try {
      await fs.access(cpgPath);
    } catch {
      throw new Error("cpg.bin not found after joern-parse");
    }

    // Step 2: joern-export
    const exportResult = await new Promise<{ data?: unknown; error?: string; success: boolean }>((resolve) => {
      const exportCmd = spawn("joern-export", ["--repr=all", "--format=graphson"], { cwd: tmpDir });
      let stdout = "";
      let stderr = "";

      exportCmd.stdout.on("data", (data: Buffer) => {
        stdout += data.toString();
      });

      exportCmd.stderr.on("data", (data: Buffer) => {
        stderr += data.toString();
      });

      exportCmd.on("close", (code) => {
        if (code === 0) {
          if (stdout.trim().startsWith("{")) {
            try {
              const parsed = JSON.parse(stdout) as unknown;
              resolve({ success: true, data: parsed });
            } catch (err) {
              resolve({ success: false, error: `Invalid JSON from stdout: ${String(err)}` });
            }
          } else {
            const outDir = path.join(tmpDir, "out");
            resolve({ success: true, data: { outDir } });
          }
        } else {
          resolve({ success: false, error: stderr || `joern-export exited with code ${String(code)}` });
        }
      });
    });

    if (!exportResult.success) {
      throw new Error(`joern-export failed: ${String(exportResult.error)}`);
    }

    // Process export result
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (exportResult.data && typeof exportResult.data === "object" && exportResult.data !== null && !("outDir" in exportResult.data)) {
      return exportResult.data as ICPGRootExport;
    }

    // Merge JSON files from output directory
    const outDir = path.join(tmpDir, "out");
    try {
      await fs.access(outDir);
    } catch {
      throw new Error("joern-export produced no output directory");
    }

    const files = await fs.readdir(outDir);
    const jsonFiles = files.filter((f) => f.toLowerCase().endsWith(".json"));

    if (jsonFiles.length === 0) {
      throw new Error("No JSON files found in joern-export output");
    }

    // Merge all JSON files
    const merged: Record<string, unknown> = {};
    for (const file of jsonFiles) {
      const filePath = path.join(outDir, file);
      const content = await fs.readFile(filePath, "utf8");
      const data = JSON.parse(content) as Record<string, unknown>;
      Object.assign(merged, data);
    }

    return merged as unknown as ICPGRootExport;
  }

  /**
   * Count methods in CPG data for validation
   */
  private countMethods(cpgData: CPGRoot): number {
    try {
      const exportData = cpgData.export;
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
      if (exportData && typeof exportData === "object" && exportData !== null && "method" in exportData) {
        const methods = exportData.method;
        if (Array.isArray(methods)) {
          return methods.length;
        }
      }
      return 0;
    } catch {
      return 0;
    }
  }
}
