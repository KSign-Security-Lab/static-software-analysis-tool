import { CPGRoot } from "../../types/cpg";
import { generateEndpointArtifacts, generateTestCases, loadCPGData } from "../helpers/dfgTestUtils";

const TEST_CASES: { cpgFile: string; expectedDfgFile: string; name: string }[] = generateTestCases().slice(0, 2); // Use first 2 for performance tests

describe.each(TEST_CASES)("DFG Performance - %s", (testCase) => {
  let cpgData: CPGRoot;

  beforeAll(() => {
    cpgData = loadCPGData(testCase.cpgFile);
  });

  it("should generate DFG within 3 seconds", async () => {
    const startTime = Date.now();
    const { endpointDFG } = await generateEndpointArtifacts(cpgData);
    const endTime = Date.now();

    const executionTime = endTime - startTime;
    expect(executionTime).toBeLessThan(3000); // 3 seconds
    expect(Array.isArray(endpointDFG)).toBe(true);
    expect(endpointDFG.length).toBeGreaterThan(0);

    console.log(`DFG generation took ${String(executionTime)}ms for ${testCase.name}`);
  });

  it("should handle multiple rapid generations", async () => {
    const iterations = 3;
    const startTime = Date.now();

    for (let i = 0; i < iterations; i++) {
      const { endpointDFG } = await generateEndpointArtifacts(cpgData);
      expect(Array.isArray(endpointDFG)).toBe(true);
    }

    const endTime = Date.now();
    const totalTime = endTime - startTime;
    const averageTime = totalTime / iterations;

    expect(averageTime).toBeLessThan(3000); // Average should be under 3 seconds
    console.log(`Average generation time over ${String(iterations)} iterations: ${String(averageTime)}ms`);
  });

  it("should maintain consistent performance across runs", async () => {
    const times: number[] = [];
    const runs = 3;

    for (let i = 0; i < runs; i++) {
      const startTime = Date.now();
      const { endpointDFG } = await generateEndpointArtifacts(cpgData);
      const endTime = Date.now();

      expect(Array.isArray(endpointDFG)).toBe(true);
      times.push(endTime - startTime);
    }

    const averageTime = times.reduce((a, b) => a + b, 0) / times.length;
    const maxTime = Math.max(...times);
    const minTime = Math.min(...times);
    const variance = maxTime - minTime;

    expect(averageTime).toBeLessThan(3000);
    expect(maxTime).toBeLessThan(5000); // Max should be under 5 seconds
    expect(variance).toBeLessThan(2000); // Variance should be reasonable

    console.log(
      `Performance stats - Avg: ${String(averageTime)}ms, Min: ${String(minTime)}ms, Max: ${String(maxTime)}ms, Variance: ${String(variance)}ms`
    );
  });

  it("should handle concurrent DFG generation", async () => {
    const concurrentRuns = 3;
    const startTime = Date.now();

    const promises = Array.from({ length: concurrentRuns }, () => generateEndpointArtifacts(cpgData));

    const results = await Promise.all(promises);
    const endTime = Date.now();

    const totalTime = endTime - startTime;

    // All results should be valid
    for (const { endpointDFG } of results) {
      expect(Array.isArray(endpointDFG)).toBe(true);
      expect(endpointDFG.length).toBeGreaterThan(0);
    }

    // Concurrent execution should complete within reasonable time
    expect(totalTime).toBeLessThan(10000); // 10 seconds for 3 concurrent runs
    console.log(`Concurrent DFG generation (${String(concurrentRuns)} runs) took ${String(totalTime)}ms`);
  });

  it("should not leak memory during repeated generation", async () => {
    const iterations = 10;
    const initialMemory = process.memoryUsage();

    for (let i = 0; i < iterations; i++) {
      const { endpointDFG } = await generateEndpointArtifacts(cpgData);
      expect(Array.isArray(endpointDFG)).toBe(true);

      // Force garbage collection if available
      if (global.gc) {
        global.gc();
      }
    }

    const finalMemory = process.memoryUsage();
    const memoryIncrease = finalMemory.heapUsed - initialMemory.heapUsed;
    const memoryIncreaseMB = memoryIncrease / 1024 / 1024;

    // Memory increase should be reasonable (less than 100MB for 10 iterations)
    expect(memoryIncreaseMB).toBeLessThan(100);
    console.log(`Memory increase after ${String(iterations)} iterations: ${memoryIncreaseMB.toFixed(2)}MB`);
  });
});
