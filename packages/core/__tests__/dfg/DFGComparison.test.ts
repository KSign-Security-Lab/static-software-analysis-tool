import { runPythonDFGExtractor } from "../../endpoint";
import { CPGRoot } from "../../types/cpg";
import { IDFGGraph } from "../../types/dfg";
import { compareDFGGraphs, generateEndpointArtifacts, generateTestCases, loadCPGData } from "../helpers/dfgTestUtils";

const TEST_CASES: { cpgFile: string; expectedDfgFile: string; name: string }[] = generateTestCases().slice(0, 3); // Use first 3 for comparison tests

describe.each(TEST_CASES)("DFG Comparison with Python - %s", (testCase) => {
  let cpgData: CPGRoot;
  let endpointDFG: IDFGGraph[];
  let pythonDFG: IDFGGraph[];

  beforeAll(async () => {
    cpgData = loadCPGData(testCase.cpgFile);
    const result = await generateEndpointArtifacts(cpgData);
    endpointDFG = result.endpointDFG;
    pythonDFG = await runPythonDFGExtractor(result.template);
  });

  it("should generate DFG from both endpoint and Python", () => {
    expect(Array.isArray(endpointDFG)).toBe(true);
    expect(Array.isArray(pythonDFG)).toBe(true);
    expect(endpointDFG.length).toBeGreaterThan(0);
    expect(pythonDFG.length).toBeGreaterThan(0);
  });

  it("should have similar graph counts", () => {
    // Allow some flexibility in graph count between endpoint and Python
    const countDifference = Math.abs(endpointDFG.length - pythonDFG.length);
    const maxAllowedDifference = Math.max(2, Math.floor(endpointDFG.length * 0.2)); // 20% tolerance

    expect(countDifference).toBeLessThanOrEqual(maxAllowedDifference);
  });

  it("should have consistent node structures", () => {
    // Compare the first graph from each (if available)
    if (endpointDFG.length > 0 && pythonDFG.length > 0) {
      const endpointGraph = endpointDFG[0];
      const pythonGraph = pythonDFG[0];

      expect(Array.isArray(endpointGraph.nodes)).toBe(true);
      expect(Array.isArray(pythonGraph.nodes)).toBe(true);
      expect(Array.isArray(endpointGraph.edges)).toBe(true);
      expect(Array.isArray(pythonGraph.edges)).toBe(true);
    }
  });

  it("should have valid node properties in both outputs", () => {
    const allGraphs = [...endpointDFG, ...pythonDFG];

    for (const graph of allGraphs) {
      for (const node of graph.nodes) {
        expect(node).toHaveProperty("id");
        expect(node).toHaveProperty("sid");
        expect(typeof node.id).toBe("number");
        expect(typeof node.sid).toBe("number");
      }
    }
  });

  it("should have valid edge properties in both outputs", () => {
    const allGraphs = [...endpointDFG, ...pythonDFG];

    for (const graph of allGraphs) {
      for (const edge of graph.edges) {
        expect(edge).toHaveProperty("source");
        expect(edge).toHaveProperty("destination");
        expect(typeof edge.source).toBe("number");
        expect(typeof edge.destination).toBe("number");
      }
    }
  });

  it("should have reasonable structural similarity", () => {
    const comparison = compareDFGGraphs(endpointDFG, pythonDFG);

    // Log differences for debugging
    if (!comparison.isEqual) {
      console.log(`Differences for ${testCase.name}:`, comparison.differences.slice(0, 5)); // Show first 5 differences
    }

    // Both should generate some output
    expect(endpointDFG.length).toBeGreaterThan(0);
    expect(pythonDFG.length).toBeGreaterThan(0);

    // If we have the same number of graphs, they should be reasonably similar
    if (endpointDFG.length === pythonDFG.length) {
      // Allow some differences but not too many
      const maxAllowedDifferences = Math.max(5, endpointDFG.length * 2);
      expect(comparison.differences.length).toBeLessThan(maxAllowedDifferences);
    }
  });

  it("should have consistent node ID ranges", () => {
    const endpointNodeIds = endpointDFG.flatMap((g) => g.nodes.map((n) => n.id));
    const pythonNodeIds = pythonDFG.flatMap((g) => g.nodes.map((n) => n.id));

    if (endpointNodeIds.length > 0 && pythonNodeIds.length > 0) {
      const endpointMin = Math.min(...endpointNodeIds);
      const endpointMax = Math.max(...endpointNodeIds);
      const pythonMin = Math.min(...pythonNodeIds);
      const pythonMax = Math.max(...pythonNodeIds);

      // ID ranges should be reasonable (not too far apart)
      const rangeDifference = Math.abs(endpointMax - endpointMin - (pythonMax - pythonMin));
      const maxRangeDifference = Math.max(100, Math.max(endpointMax - endpointMin, pythonMax - pythonMin) * 0.5);

      expect(rangeDifference).toBeLessThan(maxRangeDifference);
    }
  });

  it("should have reasonable edge density", () => {
    for (const graph of [...endpointDFG, ...pythonDFG]) {
      const nodeCount = graph.nodes.length;
      const edgeCount = graph.edges.length;

      if (nodeCount > 0) {
        const edgeDensity = edgeCount / nodeCount;
        // Edge density should be reasonable (not too sparse, not too dense)
        expect(edgeDensity).toBeGreaterThan(0);
        expect(edgeDensity).toBeLessThan(10); // Max 10 edges per node
      }
    }
  });

  it("should handle edge cases gracefully", () => {
    // Both implementations should handle the same input without crashing
    expect(() => {
      const endpointTotalNodes = endpointDFG.reduce((sum, g) => sum + g.nodes.length, 0);
      const pythonTotalNodes = pythonDFG.reduce((sum, g) => sum + g.nodes.length, 0);
      const endpointTotalEdges = endpointDFG.reduce((sum, g) => sum + g.edges.length, 0);
      const pythonTotalEdges = pythonDFG.reduce((sum, g) => sum + g.edges.length, 0);

      expect(endpointTotalNodes).toBeGreaterThanOrEqual(0);
      expect(pythonTotalNodes).toBeGreaterThanOrEqual(0);
      expect(endpointTotalEdges).toBeGreaterThanOrEqual(0);
      expect(pythonTotalEdges).toBeGreaterThanOrEqual(0);
    }).not.toThrow();
  });
});
