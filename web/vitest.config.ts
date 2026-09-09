import { dirname } from "path";
import { fileURLToPath } from "url";
import { defineConfig } from "vitest/config";

const here = dirname(fileURLToPath(import.meta.url));

const shared = {
  resolve: { alias: { "@": here } },
  oxc: { jsx: { runtime: "automatic" as const } },
};

export default defineConfig({
  ...shared,
  test: {
    projects: [
      {
        ...shared,
        test: {
          name: "lib",
          environment: "node",
          include: ["lib/**/*.test.ts", "scripts/**/*.test.ts"],
        },
      },
      {
        ...shared,
        test: {
          name: "ui",
          environment: "jsdom",
          setupFiles: ["./vitest.setup.dom.ts"],
          include: [
            "components/**/*.test.{ts,tsx}",
            "features/**/*.test.{ts,tsx}",
            "app/**/*.test.{ts,tsx}",
            "lib/**/*.test.tsx",
          ],
        },
      },
    ],
  },
});
