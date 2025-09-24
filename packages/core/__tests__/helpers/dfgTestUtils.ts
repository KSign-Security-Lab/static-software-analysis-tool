import * as fs from "fs";
import * as path from "path";

import { generateAst, generateDfg, generateTemplate } from "../../endpoint";
import { IASTResult } from "../../types/ast";
import { CPGRoot } from "../../types/cpg";
import { IDFGGraph } from "../../types/dfg";
import { TemplateNodes } from "../../types/node";

const DATA_ROOT = path.join(__dirname, "../../../../data");
const CPG_PATH = path.join(DATA_ROOT, "cpg-macro-replace");
const DFG_PATH = path.join(DATA_ROOT, "dfg");

// Function to recursively find all JSON files in a directory
function findAllJsonFiles(dir: string): string[] {
  const files: string[] = [];

  function traverse(currentDir: string) {
    const entries = fs.readdirSync(currentDir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(currentDir, entry.name);

      if (entry.isDirectory()) {
        traverse(fullPath);
      } else if (entry.name.endsWith(".json")) {
        files.push(fullPath);
      }
    }
  }

  traverse(dir);
  return files;
}

// Function to shuffle array and get random selection
function shuffleArray<T>(array: T[]): T[] {
  const shuffled = [...array];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

// Cache for test cases to avoid repeated file system scanning
let cachedTestCases: { cpgFile: string; expectedDfgFile: string; name: string }[] | null = null;

// Generate test cases dynamically
export function generateTestCases(): { cpgFile: string; expectedDfgFile: string; name: string }[] {
  // Return cached result if available
  if (cachedTestCases) {
    return cachedTestCases;
  }

  console.log("Looking for data in:", DATA_ROOT);
  console.log("CPG dir exists:", fs.existsSync(CPG_PATH));
  console.log("DFG dir exists:", fs.existsSync(DFG_PATH));

  // Find all JSON files in both directories
  const cpgFiles = findAllJsonFiles(CPG_PATH);
  const dfgFiles = findAllJsonFiles(DFG_PATH);

  console.log("Found CPG files:", cpgFiles.length);
  console.log("Found DFG files:", dfgFiles.length);

  // Filter for files that have corresponding pairs
  const validPairs: { cpgFile: string; dfgFile: string }[] = [];

  for (const cpgFile of cpgFiles) {
    const relativeCpgPath = path.relative(CPG_PATH, cpgFile);
    // Try different naming patterns
    const patterns = [
      relativeCpgPath.replace("_macro_replaced.json", "_dfg.json"),
      relativeCpgPath.replace("_macro_replaced.json", "_macro_replaced_dfg.json"),
      relativeCpgPath.replace(".json", "_dfg.json"),
    ];

    for (const expectedDfgPath of patterns) {
      const fullDfgPath = path.join(DFG_PATH, expectedDfgPath);

      if (fs.existsSync(fullDfgPath)) {
        validPairs.push({
          cpgFile: relativeCpgPath,
          dfgFile: expectedDfgPath,
        });
        break; // Found a match, move to next CPG file
      }
    }
  }

  console.log("Found valid pairs:", validPairs.length);

  // If no valid pairs found, return empty array with a fallback message
  if (validPairs.length === 0) {
    console.log("No valid test case pairs found. Using fallback test cases.");
    return [
      {
        name: "fallback_test_1",
        cpgFile: "CWE121_Stack_Based_Buffer_Overflow/s01/CWE121_Stack_Based_Buffer_Overflow__char_type_overrun_memcpy_01_macro_replaced.json",
        expectedDfgFile:
          "CWE121_Stack_Based_Buffer_Overflow/s01/CWE121_Stack_Based_Buffer_Overflow__char_type_overrun_memcpy_01_macro_replaced_dfg.json",
      },
    ];
  }

  // Sort to ensure consistent first 10
  validPairs.sort((a, b) => a.cpgFile.localeCompare(b.cpgFile));

  // Take first 10
  const first10 = validPairs.slice(0, 10);

  // Get remaining files and randomly select 20
  const remaining = validPairs.slice(10);
  const random20 = shuffleArray(remaining).slice(0, 20);

  // Combine and create test cases
  const selectedPairs = [...first10, ...random20];

  console.log("Selected test cases:", selectedPairs.length);

  const result = selectedPairs.map((pair, index) => ({
    name: `test_case_${String(index + 1)}_${path.basename(pair.cpgFile, ".json")}`,
    cpgFile: pair.cpgFile,
    expectedDfgFile: pair.dfgFile,
  }));

  // Cache the result
  cachedTestCases = result;
  return result;
}

export function loadCPGData(filePath: string): CPGRoot {
  const fullPath = path.join(CPG_PATH, filePath);
  const data = fs.readFileSync(fullPath, "utf8");
  return JSON.parse(data) as CPGRoot;
}

export function loadExpectedDFGData(filePath: string): IDFGGraph[] {
  const fullPath = path.join(DFG_PATH, filePath);
  const data = fs.readFileSync(fullPath, "utf8");
  return JSON.parse(data) as IDFGGraph[];
}

export function compareDFGGraphs(endpointDFG: IDFGGraph[], pythonDFG: IDFGGraph[]): { differences: string[]; isEqual: boolean } {
  const differences: string[] = [];

  if (endpointDFG.length !== pythonDFG.length) {
    differences.push(`Different number of graphs: endpoint=${String(endpointDFG.length)}, python=${String(pythonDFG.length)}`);
    return { isEqual: false, differences };
  }

  for (let i = 0; i < endpointDFG.length; i++) {
    const endpointGraph = endpointDFG[i];
    const pythonGraph = pythonDFG[i];

    if (endpointGraph.nodes.length !== pythonGraph.nodes.length) {
      differences.push(
        `Graph ${String(i)}: Different number of nodes: endpoint=${String(endpointGraph.nodes.length)}, python=${String(pythonGraph.nodes.length)}`
      );
    }

    if (endpointGraph.edges.length !== pythonGraph.edges.length) {
      differences.push(
        `Graph ${String(i)}: Different number of edges: endpoint=${String(endpointGraph.edges.length)}, python=${String(pythonGraph.edges.length)}`
      );
    }

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
      if ("feat" in endpointNode && "feat" in pythonNode) {
        const endpointFeat = endpointNode.feat as Record<string, unknown>;
        const pythonFeat = pythonNode.feat as Record<string, unknown>;
        for (const key of Object.keys(endpointFeat)) {
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

export async function generateEndpointArtifacts(cpgData: CPGRoot): Promise<{
  astData: IASTResult[];
  endpointDFG: IDFGGraph[];
  template: TemplateNodes[];
}> {
  try {
    const template = generateTemplate(cpgData);
    const astData = await generateAst(template);
    const endpointDFG = generateDfg(cpgData, astData);
    return { astData, endpointDFG, template };
  } catch {
    return { astData: [], endpointDFG: [], template: [] };
  }
}
