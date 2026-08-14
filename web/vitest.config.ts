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
          // `.ts` only. A `.tsx` test exists to render something, and
          // rendering wants a DOM -- `lib/run/selection.test.tsx` drives a hook
          // through a real tree and failed twelve ways in `node` before this
          // rule was written down. The extension is the honest signal.
          include: ["lib/**/*.test.ts", "scripts/**/*.test.ts"],
        },
      },
      {
        ...shared,
        test: {
          name: "ui",
          environment: "jsdom",
          // jsdom has no ResizeObserver and Radix assumes one. See the file.
          setupFiles: ["./vitest.setup.dom.ts"],
          // `features/` belongs here too. Leaving a directory out does not
          // fail, it silently runs nothing -- which is how a suite ends up
          // green while covering less than it did.
          include: [
            "components/**/*.test.{ts,tsx}",
            "features/**/*.test.{ts,tsx}",
            "app/**/*.test.{ts,tsx}",
            // A hook's own tests live beside the hook. `.tsx` because driving
            // one means rendering a component that calls it.
            "lib/**/*.test.tsx",
          ],
        },
      },
    ],
  },
});
