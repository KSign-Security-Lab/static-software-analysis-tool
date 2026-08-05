import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

/**
 * Files the rewrite deletes or replaces, exempted from the React Compiler rules
 * that eslint-config-next 16 turned on.
 *
 * Every entry fails for the same reason: it reads localStorage (or a prop) in an
 * effect and then setStates, which is the mount-time flash the workbench replaces
 * with a server-read layout cookie. The rule is right; the code is on its way out.
 *
 * This list must only ever shrink. When it is empty, delete it -- an entry that
 * outlives the file it names is how a temporary exemption becomes permanent.
 */
const REPLACED_BY_THE_WORKBENCH_REWRITE = [
  "app/agent/studio/page.tsx",
  "components/GraphExplorer.tsx",
  "components/PipelineExplorer.tsx",
  "components/studio/SpanDetail.tsx",
  "components/studio/StepCard.tsx",
  "components/workspace/CodeCanvas.tsx",
  "lib/studio/panes.ts",
];

// eslint-config-next 16 ships native flat configs, so the FlatCompat shim that
// `next lint` needed is gone -- and actively broken against it: eslintrc's
// validator tries to JSON.stringify a plugin object that now refers to itself.
const eslintConfig = [
  {
    // `next lint` applied these implicitly. The lint script calls the ESLint
    // CLI directly (next lint was removed in Next.js 16), so the ignores have
    // to be declared here or build output and deps get linted too.
    ignores: ["node_modules/**", ".next/**", "out/**", "build/**", "next-env.d.ts"],
  },
  ...coreWebVitals,
  ...typescript,
  {
    files: REPLACED_BY_THE_WORKBENCH_REWRITE,
    rules: {
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/refs": "off",
    },
  },
];

export default eslintConfig;
