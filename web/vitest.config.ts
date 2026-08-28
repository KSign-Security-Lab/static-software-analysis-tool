import { dirname } from "path";
import { fileURLToPath } from "url";
import { defineConfig } from "vitest/config";

const here = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: { "@": here },
  },
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts", "components/**/*.test.tsx"],
  },
  // App tsconfig uses jsx:"preserve" (Next compiles it); compile JSX to the
  // automatic runtime for the vitest (rolldown/oxc) transform instead.
  oxc: { jsx: { runtime: "automatic" } },
});
