// Mock the endpoint module to avoid import.meta issues in tests
jest.mock("../endpoint", () => ({
  generateTemplate: jest.fn((cpg: any) => {
    // Return mock template data
    return [
      { id: 1, type: "FUNCTION", name: "test_function" },
      { id: 2, type: "VARIABLE", name: "test_var" },
    ];
  }),

  generateAst: jest.fn(async (template: any) => {
    // Return mock AST data
    return [
      { id: 1, type: "FUNCTION_DECLARATION", name: "test_function" },
      { id: 2, type: "VARIABLE_DECLARATION", name: "test_var" },
    ];
  }),

  generateDfg: jest.fn((cpg: any, ast: any) => {
    // Return mock DFG data with proper structure
    return [
      {
        nodes: [
          {
            id: 1,
            sid: 1,
            features: {
              nodeType: "FUNCTION",
              inDegreeDFG: 0,
              outDegreeDFG: 1,
              defCount: 1,
              useCount: 0,
              isBufferAccess: false,
              isSinkAssignment: false,
              isSinkCallUnbounded: false,
              isSinkCallBounded: false,
              callDestinationIndexed: false,
              callLengthLinkedToDestination: false,
              callSizeNonConstant: false,
              callDangerUnbounded: false,
            },
            debug: {},
          },
          {
            id: 2,
            sid: 2,
            features: {
              nodeType: "VARIABLE",
              inDegreeDFG: 1,
              outDegreeDFG: 0,
              defCount: 0,
              useCount: 1,
              isBufferAccess: false,
              isSinkAssignment: false,
              isSinkCallUnbounded: false,
              isSinkCallBounded: false,
              callDestinationIndexed: false,
              callLengthLinkedToDestination: false,
              callSizeNonConstant: false,
              callDangerUnbounded: false,
            },
            debug: {},
          },
        ],
        edges: [
          {
            source: 1,
            destination: 2,
            features: { flow: "VALUE", guard: "NONE", hasLowerGuard: false, hasUpperGuard: false, upperGuardNormalization: 0 },
            debug: {},
          },
        ],
      },
      {
        nodes: [
          {
            id: 3,
            sid: 3,
            features: {
              nodeType: "CALL",
              inDegreeDFG: 0,
              outDegreeDFG: 1,
              defCount: 1,
              useCount: 0,
              isBufferAccess: false,
              isSinkAssignment: false,
              isSinkCallUnbounded: false,
              isSinkCallBounded: false,
              callDestinationIndexed: false,
              callLengthLinkedToDestination: false,
              callSizeNonConstant: false,
              callDangerUnbounded: false,
            },
            debug: {},
          },
        ],
        edges: [],
      },
    ];
  }),

  runPythonDFGExtractor: jest.fn(async (template: any) => {
    // Return mock Python DFG data with proper structure
    return [
      {
        nodes: [
          {
            id: 1,
            sid: 1,
            features: {
              nodeType: "FUNCTION",
              inDegreeDFG: 0,
              outDegreeDFG: 1,
              defCount: 1,
              useCount: 0,
              isBufferAccess: false,
              isSinkAssignment: false,
              isSinkCallUnbounded: false,
              isSinkCallBounded: false,
              callDestinationIndexed: false,
              callLengthLinkedToDestination: false,
              callSizeNonConstant: false,
              callDangerUnbounded: false,
            },
            debug: {},
          },
          {
            id: 2,
            sid: 2,
            features: {
              nodeType: "VARIABLE",
              inDegreeDFG: 1,
              outDegreeDFG: 0,
              defCount: 0,
              useCount: 1,
              isBufferAccess: false,
              isSinkAssignment: false,
              isSinkCallUnbounded: false,
              isSinkCallBounded: false,
              callDestinationIndexed: false,
              callLengthLinkedToDestination: false,
              callSizeNonConstant: false,
              callDangerUnbounded: false,
            },
            debug: {},
          },
        ],
        edges: [
          {
            source: 1,
            destination: 2,
            features: { flow: "VALUE", guard: "NONE", hasLowerGuard: false, hasUpperGuard: false, upperGuardNormalization: 0 },
            debug: {},
          },
        ],
      },
      {
        nodes: [
          {
            id: 3,
            sid: 3,
            features: {
              nodeType: "CALL",
              inDegreeDFG: 0,
              outDegreeDFG: 1,
              defCount: 1,
              useCount: 0,
              isBufferAccess: false,
              isSinkAssignment: false,
              isSinkCallUnbounded: false,
              isSinkCallBounded: false,
              callDestinationIndexed: false,
              callLengthLinkedToDestination: false,
              callSizeNonConstant: false,
              callDangerUnbounded: false,
            },
            debug: {},
          },
        ],
        edges: [],
      },
    ];
  }),
}));
