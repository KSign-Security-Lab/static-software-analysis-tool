import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

/**
 * The eight class families the old stylesheets used.
 *
 * globals.css and studio.css are gone, so nothing defines these any more --
 * which means a class from one of them now silently does nothing rather than
 * looking slightly wrong. That is worse, so it is an error.
 *
 * It also stops the prefixes coming back. There were eight of them for one
 * application, and the reason there were eight is that nothing ever said no.
 */
const DEAD_CLASS_FAMILIES = String.raw`\b(btn|card|chip|pill|tag|finding|report|snip|cbar|confgrid|confrow|checks|tb[a-z-]*|sx-[a-z-]+|tx-[a-z-]+|ws-[a-z-]+|gx-[a-z-]+|rh-[a-z-]+|rail-[a-z-]+|section-[a-z-]+|app-main|drawer[a-z-]*|topbar|topnav|srcchip|scrim|brand[a-z-]*|editor-shell|editor-bar)\b`;

// eslint-config-next 16 ships native flat configs, so the FlatCompat shim that
// `next lint` needed is gone -- and actively broken against it: eslintrc's
// validator tries to JSON.stringify a plugin object that now refers to itself.
const eslintConfig = [
  {
    // `next lint` applied these implicitly. The lint script calls the ESLint
    // CLI directly (next lint was removed in Next.js 16), so the ignores have
    // to be declared here or build output and deps get linted too.
    ignores: ["node_modules/**", ".next/**", ".next-*/**", "out/**", "build/**", "next-env.d.ts"],
  },
  ...coreWebVitals,
  ...typescript,
  {
    files: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}", "features/**/*.{ts,tsx}"],
    // `components/ui` is vendored from shadcn and only uses utilities; the
    // regex would never match it, but excluding it says so.
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
          // One EventSource per tab, owned by the shell. The server's channel
          // hands every listener its own queue now, but two in one tab still
          // means two halves of the same run in two places.
          selector: "NewExpression[callee.name='EventSource']",
          message: "Only lib/api/events.ts may construct an EventSource; subscribe through the run stream provider.",
        },
      ],
    },
  },
  {
    // The one legitimate EventSource, and the module the rule exists to protect.
    files: ["lib/api/events.ts"],
    rules: { "no-restricted-syntax": "off" },
  },
];

export default eslintConfig;
