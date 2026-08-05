import { dirname } from "path";
import { fileURLToPath } from "url";
import { defineConfig } from "vitest/config";

const here = dirname(fileURLToPath(import.meta.url));

// App tsconfig uses jsx:"preserve" (Next compiles it); compile JSX to the
// automatic runtime for the vitest (rolldown/oxc) transform instead.
const shared = {
  resolve: { alias: { "@": here } },
  oxc: { jsx: { runtime: "automatic" as const } },
};

export default defineConfig({
  ...shared,
  test: {
    // Two environments, split by what is under test rather than one setting for
    // everything. Most of the suite is pure functions over CPGs, findings and
    // trace spans: faster and more honestly scoped in node -- and one of them
    // reads a 691KB fixture off disk while another replaces `window` wholesale
    // with a stub, neither of which wants a real DOM underneath.
    projects: [
      {
        ...shared,
        test: {
          name: "lib",
          environment: "node",
          // Both extensions in both places: a component's pure helpers are
          // worth testing without dragging in JSX, and the old pattern
          // silently skipped any such file rather than failing.
          include: ["lib/**/*.test.{ts,tsx}", "scripts/**/*.test.{ts,tsx}"],
        },
      },
      {
        ...shared,
        test: {
          name: "ui",
          environment: "jsdom",
          include: ["components/**/*.test.{ts,tsx}", "app/**/*.test.{ts,tsx}"],
        },
      },
    ],
  },
});
