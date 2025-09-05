// validate.ts
import { z } from "zod";

// Generic GraphSON wrapper
const GraphSON = <T extends z.ZodTypeAny>(valueSchema: T) =>
  z.object({
    "@type": z.string(),
    "@value": valueSchema,
  });

// Primitive GraphSON value schema
const GraphSONNumber = GraphSON(z.number());

// Edge schema
const EdgeSchema = z.object({
  "@type": z.string(),
  id: GraphSONNumber,
  inV: GraphSONNumber,
  inVLabel: z.string(),
  label: z.string(),
  outV: GraphSONNumber,
  outVLabel: z.string(),
  properties: z.record(z.string(), z.any()),
});

// Vertex schema
const VertexSchema = z.object({
  "@type": z.string(),
  id: GraphSONNumber,
  label: z.string(),
  properties: z.record(z.string(), z.any()),
});

// GraphData wrapper
const GraphDataSchema = z.object({
  edges: z.array(EdgeSchema),
  vertices: z.array(VertexSchema),
});

// Single Root GraphSON schema
const SingleCPGRootSchema = GraphSON(GraphDataSchema);

// Array of Root GraphSON objects
const CPGRootArraySchema = z.array(SingleCPGRootSchema);

type CPGRoot = z.infer<typeof SingleCPGRootSchema>;

/**
 * Parses and validates unknown JSON.
 * Accepts either a single GraphSON object or an array of them.
 * @param input The raw JSON (e.g. parsed via JSON.parse or imported)
 * @throws ZodError if validation fails
 */
export function validateCPGRoot(input: unknown): CPGRoot | CPGRoot[] {
  if (Array.isArray(input)) {
    return CPGRootArraySchema.parse(input);
  }
  return SingleCPGRootSchema.parse(input);
}
