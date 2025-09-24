import { CPGRoot } from "../../types/cpg";
import { IDFGGraph } from "../../types/dfg";
import { generateEndpointArtifacts, generateTestCases, loadCPGData, loadExpectedDFGData } from "../helpers/dfgTestUtils";

const TEST_CASES: { cpgFile: string; expectedDfgFile: string; name: string }[] = generateTestCases().slice(0, 3); // Use first 3 for generation tests

describe.each(TEST_CASES)("DFG Generation - %s", (testCase) => {
  let cpgData: CPGRoot;
  let endpointDFG: IDFGGraph[];
  let expectedDFG: IDFGGraph[];

  beforeAll(async () => {
    cpgData = loadCPGData(testCase.cpgFile);
    const { endpointDFG: e } = await generateEndpointArtifacts(cpgData);
    endpointDFG = e;
    expectedDFG = loadExpectedDFGData(testCase.expectedDfgFile);
  });

  it("should generate DFG graphs", () => {
    expect(Array.isArray(endpointDFG)).toBe(true);
    expect(endpointDFG.length).toBeGreaterThan(0);
  });

  it("should have valid graph structure", () => {
    for (const graph of endpointDFG) {
      expect(graph).toHaveProperty("nodes");
      expect(graph).toHaveProperty("edges");
      expect(Array.isArray(graph.nodes)).toBe(true);
      expect(Array.isArray(graph.edges)).toBe(true);
    }
  });

  it("should have nodes with required properties", () => {
    for (const graph of endpointDFG) {
      for (const node of graph.nodes) {
        expect(node).toHaveProperty("id");
        expect(node).toHaveProperty("sid");
        expect(node).toHaveProperty("features");
        expect(node).toHaveProperty("debug");
        expect(typeof node.id).toBe("number");
        expect(typeof node.sid).toBe("number");
        expect(typeof node.features).toBe("object");
        expect(typeof node.debug).toBe("object");
      }
    }
  });

  it("should have edges with required properties", () => {
    for (const graph of endpointDFG) {
      for (const edge of graph.edges) {
        expect(edge).toHaveProperty("source");
        expect(edge).toHaveProperty("destination");
        expect(typeof edge.source).toBe("number");
        expect(typeof edge.destination).toBe("number");
      }
    }
  });

  it("should match expected DFG structure", () => {
    expect(endpointDFG.length).toBe(expectedDFG.length);
    for (let i = 0; i < expectedDFG.length; i++) {
      expect(endpointDFG[i].nodes.length).toBe(expectedDFG[i].nodes.length);
      expect(endpointDFG[i].edges.length).toBe(expectedDFG[i].edges.length);
    }
  });

  it("should have consistent node IDs", () => {
    for (const graph of endpointDFG) {
      const nodeIds = graph.nodes.map((n) => n.id);
      const uniqueIds = new Set(nodeIds);
      expect(uniqueIds.size).toBe(nodeIds.length); // All IDs should be unique
    }
  });

  it("should have valid edge references", () => {
    for (const graph of endpointDFG) {
      const nodeIds = new Set(graph.nodes.map((n) => n.id));
      for (const edge of graph.edges) {
        expect(nodeIds.has(edge.source)).toBe(true);
        expect(nodeIds.has(edge.destination)).toBe(true);
      }
    }
  });
});
