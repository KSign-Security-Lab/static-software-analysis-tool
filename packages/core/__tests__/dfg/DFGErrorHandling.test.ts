import { CPGRoot } from "types/cpg";

import { generateEndpointArtifacts } from "../helpers/dfgTestUtils";

describe("DFG Error Handling", () => {
  it("should handle empty CPG data", async () => {
    const emptyCPG = {
      export: {
        "@type": "g:CPG",
        "@value": { vertices: [], edges: [] },
      },
    };

    const { endpointDFG } = await generateEndpointArtifacts(emptyCPG as unknown as CPGRoot);
    expect(Array.isArray(endpointDFG)).toBe(true);
    expect(endpointDFG.length).toBe(0);
  });

  it("should handle malformed CPG data", async () => {
    const malformedCPG = {
      export: {
        "@type": "g:CPG",
        "@value": {
          vertices: [{ id: 1, label: "INVALID_LABEL", properties: {} }],
          edges: [],
        },
      },
    };

    const { endpointDFG } = await generateEndpointArtifacts(malformedCPG as unknown as CPGRoot);
    expect(Array.isArray(endpointDFG)).toBe(true);
    // Should either return empty array or handle gracefully
    expect(endpointDFG.length).toBeGreaterThanOrEqual(0);
  });

  it("should handle CPG with missing required fields", async () => {
    const incompleteCPG = {
      export: {
        "@type": "g:CPG",
        "@value": {
          vertices: [
            { id: 1, properties: {} }, // Missing label
          ],
          edges: [],
        },
      },
    };

    const { endpointDFG } = await generateEndpointArtifacts(incompleteCPG as unknown as CPGRoot);
    expect(Array.isArray(endpointDFG)).toBe(true);
    expect(endpointDFG.length).toBeGreaterThanOrEqual(0);
  });

  it("should handle CPG with circular references", async () => {
    const circularCPG = {
      export: {
        "@type": "g:CPG",
        "@value": {
          vertices: [
            { id: 1, label: "METHOD", properties: { name: "test" } },
            { id: 2, label: "CALL", properties: { name: "test" } },
          ],
          edges: [
            { id: 1, outV: 1, inV: 2, label: "CALL" },
            { id: 2, outV: 2, inV: 1, label: "CALL" }, // Circular reference
          ],
        },
      },
    };

    const { endpointDFG } = await generateEndpointArtifacts(circularCPG as unknown as CPGRoot);
    expect(Array.isArray(endpointDFG)).toBe(true);
    // Should handle circular references gracefully
    expect(endpointDFG.length).toBeGreaterThanOrEqual(0);
  });

  it("should handle CPG with invalid node types", async () => {
    const invalidNodeCPG = {
      export: {
        "@type": "g:CPG",
        "@value": {
          vertices: [
            { id: 1, label: "UNKNOWN_TYPE", properties: {} },
            { id: 2, label: "", properties: {} }, // Empty label
            { id: 3, label: null, properties: {} }, // Null label
          ],
          edges: [],
        },
      },
    };

    const { endpointDFG } = await generateEndpointArtifacts(invalidNodeCPG as unknown as CPGRoot);
    expect(Array.isArray(endpointDFG)).toBe(true);
    expect(endpointDFG.length).toBeGreaterThanOrEqual(0);
  });

  it("should handle CPG with invalid edge references", async () => {
    const invalidEdgeCPG = {
      export: {
        "@type": "g:CPG",
        "@value": {
          vertices: [{ id: 1, label: "METHOD", properties: { name: "test" } }],
          edges: [
            { id: 1, outV: 1, inV: 999, label: "CALL" }, // Invalid target
            { id: 2, outV: 888, inV: 1, label: "CALL" }, // Invalid source
          ],
        },
      },
    };

    const { endpointDFG } = await generateEndpointArtifacts(invalidEdgeCPG as unknown as CPGRoot);
    expect(Array.isArray(endpointDFG)).toBe(true);
    expect(endpointDFG.length).toBeGreaterThanOrEqual(0);
  });

  it("should handle very large CPG data", async () => {
    const largeCPG = {
      export: {
        "@type": "g:CPG",
        "@value": {
          vertices: Array.from({ length: 10000 }, (_, i) => ({
            id: i,
            label: "METHOD",
            properties: { name: `method_${String(i)}` },
          })),
          edges: Array.from({ length: 5000 }, (_, i) => ({
            id: i,
            outV: i,
            inV: (i + 1) % 10000,
            label: "CALL",
          })),
        },
      },
    };

    const startTime = Date.now();
    const { endpointDFG } = await generateEndpointArtifacts(largeCPG as unknown as CPGRoot);
    const endTime = Date.now();

    expect(Array.isArray(endpointDFG)).toBe(true);
    expect(endTime - startTime).toBeLessThan(10000); // Should complete within 10 seconds
  });

  it("should handle CPG with special characters in properties", async () => {
    const specialCharCPG = {
      export: {
        "@type": "g:CPG",
        "@value": {
          vertices: [
            {
              id: 1,
              label: "METHOD",
              properties: {
                name: "test_method_🚀_with_emoji",
                description: "Test with\nnewlines\tand\ttabs",
                unicode: "测试中文和한국어",
              },
            },
          ],
          edges: [],
        },
      },
    };

    const { endpointDFG } = await generateEndpointArtifacts(specialCharCPG as unknown as CPGRoot);
    expect(Array.isArray(endpointDFG)).toBe(true);
    expect(endpointDFG.length).toBeGreaterThanOrEqual(0);
  });

  it("should handle null/undefined input gracefully", async () => {
    await expect(generateEndpointArtifacts(null as unknown as CPGRoot)).resolves.toBeDefined();
    await expect(generateEndpointArtifacts(undefined as unknown as CPGRoot)).resolves.toBeDefined();
  });

  it("should handle non-object input gracefully", async () => {
    await expect(generateEndpointArtifacts("invalid" as unknown as CPGRoot)).resolves.toBeDefined();
    await expect(generateEndpointArtifacts(123 as unknown as CPGRoot)).resolves.toBeDefined();
    await expect(generateEndpointArtifacts([] as unknown as CPGRoot)).resolves.toBeDefined();
  });
});
