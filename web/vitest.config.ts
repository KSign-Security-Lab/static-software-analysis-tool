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
    // Both extensions in both places: a component's pure helpers are worth
    // testing without dragging in JSX, and the old pattern silently skipped
    // any such file rather than failing.
    include: ["lib/**/*.test.{ts,tsx}", "components/**/*.test.{ts,tsx}"],
  },
  // App tsconfig uses jsx:"preserve" (Next compiles it); compile JSX to the
  // automatic runtime for the vitest (rolldown/oxc) transform instead.
  oxc: { jsx: { runtime: "automatic" } },
});
