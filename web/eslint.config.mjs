import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

const DEAD_CLASS_FAMILIES = String.raw`\b(btn|card|chip|pill|tag|finding|report|snip|cbar|confgrid|confrow|checks|tb[a-z-]*|sx-[a-z-]+|tx-[a-z-]+|ws-[a-z-]+|gx-[a-z-]+|rh-[a-z-]+|rail-[a-z-]+|section-[a-z-]+|app-main|drawer[a-z-]*|topbar|topnav|srcchip|scrim|brand[a-z-]*|editor-shell|editor-bar)\b`;

const eslintConfig = [
  {
    ignores: ["node_modules/**", ".next/**", ".next-*/**", "out/**", "build/**", "next-env.d.ts"],
  },
  ...coreWebVitals,
  ...typescript,
  {
    files: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}", "features/**/*.{ts,tsx}"],
    ignores: ["components/ui/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: `JSXAttribute[name.name='className'] Literal[value=/${DEAD_CLASS_FAMILIES}/]`,
          message:
            "This class family belonged to globals.css or studio.css, both deleted. Nothing defines it, so it does nothing. Use a utility or a component in components/ui.",
        },
        {
          selector: "NewExpression[callee.name='EventSource']",
          message: "Only lib/api/events.ts may construct an EventSource; subscribe through the run stream provider.",
        },
      ],
    },
  },
  {
    files: ["lib/api/events.ts"],
    rules: { "no-restricted-syntax": "off" },
  },
];

export default eslintConfig;
