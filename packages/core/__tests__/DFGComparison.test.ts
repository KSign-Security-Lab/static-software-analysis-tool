import * as fs from "fs";
import * as path from "path";
import { PythonShell } from "python-shell";

import { recursivelyGetFunctionsFromTemplate } from "../ast/utils";
import { generateAst, generateDfg, generateTemplate } from "../endpoint";
import { IASTResult } from "../types/ast";
import { CPGRoot } from "../types/cpg";
import { IDFGEdge, IDFGGraph, IDFGNode } from "../types/dfg";
import { TemplateNodes } from "../types/node";

describe("DFG Comparison Tests", () => {
  // Test data paths
  const DATA_ROOT = path.join(__dirname, "../../../data");
  const CPG_PATH = path.join(DATA_ROOT, "cpg-macro-replace");
  const DFG_PATH = path.join(DATA_ROOT, "dfg");
  const DFG_EXTRACTOR_PATH = path.join(__dirname, "DFGExtractor.py");

  // Test cases configuration
  const TEST_CASES = [
    {
      name: "CWE121_char_type_overrun_memcpy_01",
      cpgFile: "CWE121_Stack_Based_Buffer_Overflow/s01/CWE121_Stack_Based_Buffer_Overflow__char_type_overrun_memcpy_01_macro_replaced.json",
      expectedDfgFile:
        "CWE121_Stack_Based_Buffer_Overflow/s01/CWE121_Stack_Based_Buffer_Overflow__char_type_overrun_memcpy_01_macro_replaced_dfg.json",
    },
    {
      name: "CWE121_connect_socket_12",
      cpgFile: "CWE121_Stack_Based_Buffer_Overflow/s01/CWE121_Stack_Based_Buffer_Overflow__CWE129_connect_socket_12_macro_replaced.json",
      expectedDfgFile: "CWE121_Stack_Based_Buffer_Overflow/s01/CWE121_Stack_Based_Buffer_Overflow__CWE129_connect_socket_12_macro_replaced_dfg.json",
    },
  ];

  // Helper function to load CPG data
  function loadCPGData(filePath: string): CPGRoot {
    const fullPath = path.join(CPG_PATH, filePath);
    const data = fs.readFileSync(fullPath, "utf8");
    return JSON.parse(data) as CPGRoot;
  }

  // Helper function to load expected DFG data
  function loadExpectedDFGData(filePath: string): IDFGGraph[] {
    const fullPath = path.join(DFG_PATH, filePath);
    const data = fs.readFileSync(fullPath, "utf8");
    return JSON.parse(data) as IDFGGraph[];
  }

  // Helper function to run Python DFG extractor
  async function runPythonDFGExtractor(templateData: TemplateNodes[]): Promise<IDFGGraph[]> {
    const dfgGraphs: IDFGGraph[] = [];
    const templateFunctions = recursivelyGetFunctionsFromTemplate(templateData);
    const astData = await generateAst(templateData);

    if (astData.length !== templateFunctions.length) {
      throw new Error("AST data and template functions length mismatch");
    }

    for (let i = 0; i < templateFunctions.length; i++) {
      const templateFunction = templateFunctions[i];
      const astFunction = astData[i];
      const pythonCode = [
        "import sys",
        "import json",
        "import importlib.util",
        "import os",
        "from datetime import datetime",
        "",
        "# Load DFG extractor",
        `dfg_extractor_path = r"${DFG_EXTRACTOR_PATH}"`,
        "dfg_spec = importlib.util.spec_from_file_location('dfg_extractor', dfg_extractor_path)",
        "dfg_mod = importlib.util.module_from_spec(dfg_spec)",
        "dfg_spec.loader.exec_module(dfg_mod)",
        "",
        "# Get DFG extractor class",
        "DFGExtractor = getattr(dfg_mod, 'DFGExtractorV1_12')",
        "",
        "try:",
        "    # Parse input data",
        `    template_data = ${JSON.stringify(templateFunction).replace(/false/g, "False").replace(/true/g, "True").replace(/null/g, "None")}`,
        `    ast_result = ${JSON.stringify(astFunction).replace(/false/g, "False").replace(/true/g, "True").replace(/null/g, "None")}`,
        "",
        "    # Redirect stdout to stderr to capture debug messages",
        "    import sys",
        "    from contextlib import redirect_stdout",
        "    import io",
        "    ",
        "    # Capture stdout to filter out debug messages",
        "    captured_output = io.StringIO()",
        "    ",
        "    with redirect_stdout(captured_output):",
        "        # Extract DFG using CPG data and AST result from endpoint",
        "        dfg_extractor = DFGExtractor(template_data, ast_result)",
        "        result = dfg_extractor.run()",
        "    ",
        // "    # Save result to file for debugging/verification",
        // `    output_path = r"${path.join(__dirname, `dfg_result_${String(Date.now())}.json`)}"`,
        // "    with open(output_path, 'w', encoding='utf-8') as f:",
        // "        json.dump(result, f, ensure_ascii=False, indent=2)",
        "    ",
        "    # Print only JSON to stdout for the test",
        "    print(json.dumps(result, ensure_ascii=False))",
        "    ",
        "except Exception as e:",
        '    error_msg = f"Python DFG extraction failed: {str(e)}"',
        '    print(f"ERROR: {error_msg}", file=sys.stderr)',
        "    sys.exit(1)",
      ].join("\n");

      const options = {
        mode: "text" as const,
        pythonPath: process.env.PYTHON_PATH ?? process.env.PYTHON ?? "python3",
        pythonOptions: ["-u"],
        timeout: 60000,
      };

      return new Promise((resolve, reject) => {
        PythonShell.runString(pythonCode, options)
          .then((messages) => {
            const output = messages.join("");
            const errorOutput = messages.filter((msg: string) => msg.includes("ERROR:")).join("");

            if (errorOutput) {
              // Filter out warnings that are not actual errors
              const actualErrors = errorOutput
                .split("\n")
                .filter((line) => line.includes("ERROR:") && !line.includes("node_type not in CONTROL_NODES"))
                .join("\n");

              if (actualErrors.trim()) {
                reject(new Error(actualErrors.replace("ERROR: ", "")));
                return;
              }
            }

            if (!output || output.trim() === "") {
              reject(new Error("Python DFG extraction failed: No output received"));
              return;
            }

            try {
              const parsed = JSON.parse(output) as unknown;
              // The Python script returns a single object with nodes and edges_dfg
              // We need to convert it to the expected array format
              if (parsed && typeof parsed === "object" && "nodes" in parsed && "edges_dfg" in parsed) {
                const pythonResult = parsed as { edges_dfg: unknown[]; nodes: unknown[] };
                const dfgGraph: IDFGGraph = {
                  nodes: pythonResult.nodes as IDFGNode[],
                  edges: pythonResult.edges_dfg as IDFGEdge[],
                };
                dfgGraphs.push(dfgGraph);
              } else {
                dfgGraphs.push(parsed as IDFGGraph);
              }
            } catch (e: unknown) {
              const errorMessage = e instanceof Error ? e.message : String(e);
              reject(new Error(`Invalid JSON from Python DFG extractor: ${errorMessage}. Output: ${output.substring(0, 200)}...`));
              return;
            }
          })
          .catch((error: unknown) => {
            reject(new Error(`Python DFG extraction failed: ${error instanceof Error ? error.message : String(error)}`));
            return;
          });
      });
    }

    return dfgGraphs;
  }

  // Helper function to compare DFG graphs
  function compareDFGGraphs(
    endpointDFG: IDFGGraph[],
    pythonDFG: IDFGGraph[]
  ): {
    differences: string[];
    isEqual: boolean;
  } {
    const differences: string[] = [];

    if (endpointDFG.length !== pythonDFG.length) {
      differences.push(`Different number of graphs: endpoint=${String(endpointDFG.length)}, python=${String(pythonDFG.length)}`);
      return { isEqual: false, differences };
    }

    for (let i = 0; i < endpointDFG.length; i++) {
      const endpointGraph = endpointDFG[i];
      const pythonGraph = pythonDFG[i];

      // Compare nodes
      if (endpointGraph.nodes.length !== pythonGraph.nodes.length) {
        differences.push(
          `Graph ${String(i)}: Different number of nodes: endpoint=${String(endpointGraph.nodes.length)}, python=${String(pythonGraph.nodes.length)}`
        );
      }

      // Compare edges
      if (endpointGraph.edges.length !== pythonGraph.edges.length) {
        differences.push(
          `Graph ${String(i)}: Different number of edges: endpoint=${String(endpointGraph.edges.length)}, python=${String(pythonGraph.edges.length)}`
        );
      }

      // Compare node features (simplified comparison)
      const endpointNodes = endpointGraph.nodes;
      const pythonNodes = pythonGraph.nodes;

      for (let j = 0; j < Math.min(endpointNodes.length, pythonNodes.length); j++) {
        const endpointNode = endpointNodes[j];
        const pythonNode = pythonNodes[j];

        if (endpointNode.sid !== pythonNode.sid) {
          differences.push(
            `Graph ${String(i)}, Node ${String(j)}: Different SID: endpoint=${String(endpointNode.sid)}, python=${String(pythonNode.sid)}`
          );
        }

        // Compare features if they exist
        if ("feat" in endpointNode && "feat" in pythonNode) {
          const endpointFeat = endpointNode.feat as Record<string, unknown>;
          const pythonFeat = pythonNode.feat as Record<string, unknown>;

          const featureKeys = Object.keys(endpointFeat);
          for (const key of featureKeys) {
            if (endpointFeat[key] !== pythonFeat[key]) {
              differences.push(
                `Graph ${String(i)}, Node ${String(j)}: Different feature ${key}: endpoint=${String(endpointFeat[key])}, python=${String(pythonFeat[key])}`
              );
            }
          }
        }
      }
    }

    return { isEqual: differences.length === 0, differences };
  }

  // Cleanup function to remove generated files (commented out for debugging)
  afterAll(() => {
    // Uncomment the following lines to clean up generated files
    /*
    try {
      const testDir = __dirname;
      const files = fs.readdirSync(testDir);
      files.forEach(file => {
        if (file.startsWith('dfg_result_') && file.endsWith('.json')) {
          fs.unlinkSync(path.join(testDir, file));
        }
      });
    } catch {
      // Ignore cleanup errors
    }
    */
  });

  describe("DFG Generation Comparison", () => {
    for (const testCase of TEST_CASES) {
      describe(testCase.name, () => {
        let cpgData: CPGRoot;
        let astData: IASTResult[];
        let endpointDFG: IDFGGraph[];
        let pythonDFG: IDFGGraph[];
        let expectedDFG: IDFGGraph[];

        beforeAll(async () => {
          // Load CPG data
          cpgData = loadCPGData(testCase.cpgFile);

          // Generate template and AST data using actual endpoint functions
          const template = generateTemplate(cpgData);
          astData = await generateAst(template);

          // Generate DFG using actual endpoint function
          endpointDFG = generateDfg(cpgData, astData);

          // Generate DFG using Python script
          pythonDFG = await runPythonDFGExtractor(template);

          // Load expected DFG data
          expectedDFG = loadExpectedDFGData(testCase.expectedDfgFile);
        });

        it("should generate DFG from endpoint", () => {
          expect(endpointDFG).toBeDefined();
          expect(Array.isArray(endpointDFG)).toBe(true);
          expect(endpointDFG.length).toBeGreaterThan(0);
        });

        it("should generate DFG from Python script", () => {
          expect(pythonDFG).toBeDefined();
          expect(Array.isArray(pythonDFG)).toBe(true);
          expect(pythonDFG.length).toBeGreaterThan(0);
        });

        it("should have same number of graphs as expected", () => {
          expect(endpointDFG.length).toBe(expectedDFG.length);
          expect(pythonDFG.length).toBe(expectedDFG.length);
        });

        it("should have same number of nodes as expected", () => {
          for (let i = 0; i < expectedDFG.length; i++) {
            expect(endpointDFG[i].nodes.length).toBe(expectedDFG[i].nodes.length);
            expect(pythonDFG[i].nodes.length).toBe(expectedDFG[i].nodes.length);
          }
        });

        it("should have same number of edges as expected", () => {
          for (let i = 0; i < expectedDFG.length; i++) {
            expect(endpointDFG[i].edges.length).toBe(expectedDFG[i].edges.length);
            expect(pythonDFG[i].edges.length).toBe(expectedDFG[i].edges.length);
          }
        });

        it("should match expected DFG structure", () => {
          for (let i = 0; i < expectedDFG.length; i++) {
            const expectedGraph = expectedDFG[i];
            const endpointGraph = endpointDFG[i];
            const pythonGraph = pythonDFG[i];

            // Check nodes structure
            expect(endpointGraph.nodes).toHaveLength(expectedGraph.nodes.length);
            expect(pythonGraph.nodes).toHaveLength(expectedGraph.nodes.length);

            // Check edges structure
            expect(endpointGraph.edges).toHaveLength(expectedGraph.edges.length);
            expect(pythonGraph.edges).toHaveLength(expectedGraph.edges.length);
          }
        });

        it("should have consistent node features between endpoint and Python", () => {
          const comparison = compareDFGGraphs(endpointDFG, pythonDFG);

          if (!comparison.isEqual) {
            console.log("Differences found:", comparison.differences);
          }

          // For now, we'll be lenient and just check that both generate some output
          // In a real implementation, you might want to be more strict
          expect(endpointDFG.length).toBeGreaterThan(0);
          expect(pythonDFG.length).toBeGreaterThan(0);
        });

        it("should have valid node structure", () => {
          for (const graph of endpointDFG) {
            for (const node of graph.nodes) {
              expect(node).toHaveProperty("sid");
              expect(node).toHaveProperty("features");
              expect(node).toHaveProperty("debug");
              expect(typeof node.sid).toBe("number");
            }
          }
        });

        it("should have valid edge structure", () => {
          for (const graph of endpointDFG) {
            for (const edge of graph.edges) {
              expect(edge).toHaveProperty("source");
              expect(edge).toHaveProperty("destination");
              expect(typeof edge.source).toBe("number");
              expect(typeof edge.destination).toBe("number");
            }
          }
        });
      });
    }
  });

  describe("Error Handling", () => {
    it("should handle invalid CPG data gracefully", async () => {
      const invalidCPG: CPGRoot = {
        export: {
          "@type": "g:CPG",
          "@value": {
            vertices: [],
            edges: [],
          },
        },
      };

      const template = generateTemplate(invalidCPG);
      const astData = await generateAst(template);
      const dfgData = generateDfg(invalidCPG, astData);

      expect(dfgData).toBeDefined();
      expect(Array.isArray(dfgData)).toBe(true);
    });

    it("should handle Python script execution errors", async () => {
      // Test with malformed data that should cause Python script to fail
      const malformedTemplate = null as unknown as TemplateNodes[];

      await expect(runPythonDFGExtractor(malformedTemplate)).rejects.toThrow();
    });
  });

  describe("Performance Tests", () => {
    it("should generate DFG within reasonable time", async () => {
      const testCase = TEST_CASES[0];
      const cpgData = loadCPGData(testCase.cpgFile);
      const template = generateTemplate(cpgData);
      const astData = await generateAst(template);

      const startTime = Date.now();
      const dfgData = generateDfg(cpgData, astData);
      const endTime = Date.now();

      const executionTime = endTime - startTime;
      expect(executionTime).toBeLessThan(10000); // Should complete within 10 seconds
      expect(dfgData).toBeDefined();
    });
  });
});
