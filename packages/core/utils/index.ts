import { CPGRoot } from "../types/cpg";

export function randomIntWithLength(length: number): number {
  if (length <= 0) throw new Error("Length must be positive");

  const min = 10 ** (length - 1);
  const max = 10 ** length - 1;

  return Math.floor(Math.random() * (max - min + 1)) + min;
}

export function getFilenameFromCPG(cpg: CPGRoot): string {
  try {
    const vertices = (cpg.export as unknown as { "@value": { vertices: unknown[] } })["@value"].vertices as {
      label: string;
      properties?: Record<string, unknown>;
    }[];
    if (!Array.isArray(vertices)) return "";

    // Prefer METHOD vertex filename
    const method = vertices.find((v) => v.label === "METHOD");
    const hasGraphsonStringArray = (val: unknown): val is Record<string, Record<string, unknown>> => {
      if (!val || typeof val !== "object") return false;
      const outer = val as Record<string, unknown>;
      const inner = outer["@value"] as Record<string, unknown> | undefined;
      if (!inner || typeof inner !== "object") return false;
      const arr = inner["@value"];
      return Array.isArray(arr) && typeof arr[0] === "string";
    };

    const tryRead = (props?: Record<string, unknown>): string => {
      if (!props) return "";
      const graphson = props.FILENAME;
      if (hasGraphsonStringArray(graphson)) {
        const inner = graphson["@value"];
        const arr = inner["@value"] as unknown[];
        const first = arr[0];
        if (typeof first === "string") return first;
      }
      return "";
    };

    const fromMethod = tryRead(method?.properties);
    if (fromMethod) return fromMethod;

    // Fallback to TYPE_DECL or NAMESPACE_BLOCK
    for (const label of ["TYPE_DECL", "NAMESPACE_BLOCK"]) {
      const v = vertices.find((x) => x.label === label);
      const name = tryRead(v?.properties);
      if (name) return name;
    }
  } catch {
    // ignore
  }
  return "";
}
