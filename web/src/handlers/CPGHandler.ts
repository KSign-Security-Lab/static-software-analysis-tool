// cpgHandler.ts
import { promises as fs } from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { randomUUID } from "node:crypto";
import type { CPGRoot, ICPGRootExport } from "@ssat/core/types/cpg";

type ExecResult = {
  success: boolean;
  stdout: string;
  stderr?: string;
  uuid?: string;
};

type GetCPGOptions = {
  /**
   * Optional filename to use for the C source (must end with .c).
   * Defaults to "main.c".
   */
  filename?: string;
  /**
   * Optional Joern project name. If omitted, a deterministic name is generated.
   */
  projectName?: string;
  /**
   * If true, delete the Joern project after probing.
   */
  cleanAfter?: boolean;
  /**
   * If true, delete the temporary directory that holds the source after import.
   * Defaults to true to avoid disk buildup.
   */
  cleanupTempDir?: boolean;
};

const stringify = (v: string): string => JSON.stringify(v);

class CPGHandler {
  private readonly baseUrl: string;

  constructor(baseUrl = "http://localhost:8080") {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  // ---------- Low-level HTTP/exec helpers ----------

  private async exec(query: string): Promise<ExecResult> {
    const res = await fetch(`${this.baseUrl}/query-sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Joern HTTP ${res.status}: ${text}`);
    }

    const data = (await res.json()) as unknown;
    if (typeof data !== "object" || data === null || !("success" in data) || typeof (data as { success: unknown }).success !== "boolean") {
      throw new Error("Unexpected Joern response shape");
    }

    const result = data as ExecResult;
    if (!result.success) {
      throw new Error(`Joern query failed: ${result.stderr ?? result.stdout}`);
    }
    return result;
  }

  private qImport(inputPath: string, projectName: string, language = "c"): string {
    // Use explicit language "c" since we know the code is C.
    return `importCode(${stringify(inputPath)}, ${stringify(projectName)}, ${stringify(language)})`;
  }

  private qOpen(projectName: string): string {
    return `open(${stringify(projectName)})`;
  }

  private qClose(projectName: string): string {
    return `close(${stringify(projectName)})`;
  }

  private qDelete(projectName: string): string {
    return `delete(${stringify(projectName)})`;
  }

  private mkProjectName(seed: string): string {
    // Deterministic-ish: base + short id derived from seed bytes
    const base = "c-src";
    const raw = Buffer.from(seed, "utf8").subarray(0, 12);
    const id = Array.from(raw, (b) => b.toString(16).padStart(2, "0"))
      .join("")
      .slice(0, 8);
    return `${base}-${id}`;
  }

  // ---------- Temp filesystem helpers ----------

  private async writeTempCSource(cSource: string, filename = "main.c"): Promise<{ dir: string; file: string }> {
    if (!filename.endsWith(".c")) {
      throw new Error(`filename must end with ".c": received "${filename}"`);
    }
    const tmpRoot = path.join(os.tmpdir(), "joern-cpg-src");
    await fs.mkdir(tmpRoot, { recursive: true });

    // Use a subdir per request to avoid collisions.
    const dir = path.join(tmpRoot, randomUUID());
    await fs.mkdir(dir, { recursive: true });

    const file = path.join(dir, filename);
    const content = cSource.endsWith("\n") ? cSource : `${cSource}\n`;
    await fs.writeFile(file, content, "utf8");

    return { dir, file };
  }

  private async rimraf(targetPath: string): Promise<void> {
    // Best-effort removal; ignore non-existent.
    try {
      await fs.rm(targetPath, { recursive: true, force: true });
    } catch {
      // ignore
    }
  }

  // ---------- Public API ----------

  /**
   * Build a CPG from a *string of C code*.
   *
   * Steps:
   * 1) Write `cSource` to a temp directory as `<filename>` (default "main.c").
   * 2) Import that directory into Joern with language "c".
   * 3) Open the project and probe it (method count).
   * 4) Optional cleanup:
   *    - delete the Joern project if `cleanAfter` is true
   *    - remove the temp directory if `cleanupTempDir` is true (default)
   */
  async getCPG(cSource: string, opts: GetCPGOptions = {}): Promise<{ projectName: string; methodCount: number; sourceDir: string }> {
    const filename = opts.filename ?? "main.c";
    const { dir: sourceDir } = await this.writeTempCSource(cSource, filename);

    const projectName = opts.projectName ?? this.mkProjectName(`${filename}:${cSource.slice(0, 64)}`);

    try {
      // Import and open
      await this.exec(this.qImport(sourceDir, projectName, "c"));
      await this.exec(this.qOpen(projectName));

      // Probe to confirm graph was built
      const probe = await this.exec("println(cpg.method.name.l.size)");
      const match = probe.stdout.match(/(\d+)\s*$/);
      const methodCount = match ? Number(match[1]) : 0;

      // Optional project cleanup
      if (opts.cleanAfter) {
        await this.deleteProject(projectName);
      }

      return { projectName, methodCount, sourceDir };
    } finally {
      // Clean temp dir by default (to avoid buildup). Keep if explicitly disabled.
      if (opts.cleanupTempDir !== false) {
        await this.rimraf(sourceDir);
      }
    }
  }

  /**
   * Run a Joern query against a specific project.
   * Ensures the project is active before executing.
   */
  async runQuery(projectName: string, query: string): Promise<string> {
    await this.exec(this.qOpen(projectName));
    const res = await this.exec(query);
    return res.stdout;
  }

  /**
   * Close and delete a single project from Joern's workspace.
   */
  async deleteProject(projectName: string): Promise<void> {
    try {
      await this.exec(this.qClose(projectName));
    } catch {
      // ignore if not open
    }
    await this.exec(this.qDelete(projectName));
  }

  /**
   * Generate CPG data using joern-parse and joern-export commands.
   * This is the correct way to generate CPG data, not through the server API.
   */
  private async generateCPGFromFile(sourceFile: string): Promise<CPGRoot> {
    const { spawn } = await import("child_process");
    const { promises: fs } = await import("fs");
    const path = await import("path");
    const os = await import("os");
    const { randomUUID } = await import("crypto");

    // Create a temporary directory for joern processing
    const tmpDir = path.join(os.tmpdir(), `joern-cpg-${randomUUID()}`);
    await fs.mkdir(tmpDir, { recursive: true });

    try {
      // Step 1: joern-parse
      const parseResult = await new Promise<{ success: boolean; error?: string }>((resolve) => {
        const parse = spawn("joern-parse", [sourceFile], { cwd: tmpDir });
        let stderr = "";

        parse.stderr.on("data", (data) => {
          stderr += data.toString();
        });

        parse.on("close", (code) => {
          if (code === 0) {
            resolve({ success: true });
          } else {
            resolve({ success: false, error: stderr || `joern-parse exited with code ${code}` });
          }
        });
      });

      if (!parseResult.success) {
        throw new Error(`joern-parse failed: ${parseResult.error}`);
      }

      // Check if cpg.bin was created
      const cpgPath = path.join(tmpDir, "cpg.bin");
      try {
        await fs.access(cpgPath);
      } catch {
        throw new Error("cpg.bin not found after joern-parse");
      }

      // Step 2: joern-export
      type ExportData = Record<string, unknown> | { outDir: string };
      const exportResult = await new Promise<{ success: boolean; data?: ExportData; error?: string }>((resolve) => {
        const exportCmd = spawn("joern-export", ["--repr=all", "--format=graphson"], { cwd: tmpDir });
        let stdout = "";
        let stderr = "";

        exportCmd.stdout.on("data", (data) => {
          stdout += data.toString();
        });

        exportCmd.stderr.on("data", (data) => {
          stderr += data.toString();
        });

        exportCmd.on("close", (code) => {
          if (code === 0) {
            // Check if JSON was output to stdout
            if (stdout.trim().startsWith("{")) {
              try {
                const parsed = JSON.parse(stdout);
                resolve({ success: true, data: parsed });
              } catch (err) {
                resolve({ success: false, error: `Invalid JSON from stdout: ${err}` });
              }
            } else {
              // Check for output directory
              const outDir = path.join(tmpDir, "out");
              resolve({ success: true, data: { outDir } });
            }
          } else {
            resolve({ success: false, error: stderr || `joern-export exited with code ${code}` });
          }
        });
      });

      if (!exportResult.success) {
        throw new Error(`joern-export failed: ${exportResult.error}`);
      }

      // If we got JSON directly, format it as CPGRoot structure
      if (exportResult.data && !("outDir" in exportResult.data)) {
        return {
          export: (exportResult.data as unknown) as ICPGRootExport,
        } satisfies CPGRoot;
      }

      // Otherwise, merge JSON files from output directory
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

      // Format the data as CPGRoot structure
      return {
        export: merged as unknown as ICPGRootExport,
      } satisfies CPGRoot;
    } finally {
      // Clean up temporary directory
      try {
        await fs.rm(tmpDir, { recursive: true, force: true });
      } catch {
        // Ignore cleanup errors
      }
    }
  }

  /**
   * Get CPG data from C source code.
   * This uses joern-parse and joern-export commands directly.
   */
  async getCPGData(cSource: string, opts: GetCPGOptions = {}): Promise<CPGRoot> {
    const filename = opts.filename ?? "main.c";
    const { dir: sourceDir, file: sourceFile } = await this.writeTempCSource(cSource, filename);

    try {
      // Generate CPG data using joern-parse and joern-export
      const cpgData = await this.generateCPGFromFile(sourceFile);
      return cpgData;
    } finally {
      // Clean temp dir by default (to avoid buildup). Keep if explicitly disabled.
      if (opts.cleanupTempDir !== false) {
        await this.rimraf(sourceDir);
      }
    }
  }

  /**
   * Nuclear option: reset the entire Joern workspace on disk.
   * Use when many requests have piled up state/cache.
   */
  async resetWorkspace(): Promise<void> {
    await this.exec("workspace.reset");
  }
}

const cpgHandler = new CPGHandler();
export default cpgHandler;
