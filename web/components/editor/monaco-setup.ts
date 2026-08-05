import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";

/**
 * Load Monaco from the bundle, not from a CDN.
 *
 * `@monaco-editor/react` ships `@monaco-editor/loader`, which defaults to
 * fetching the editor from cdn.jsdelivr.net at runtime. `monaco-editor` was in
 * package.json all along but only ever imported for its *types*, so the code
 * that actually ran came from the internet: on an air-gapped or
 * egress-restricted box the editor simply never appeared, and everywhere else
 * the artifact being executed was not the one the licence gate checked.
 *
 * Must run before the first <Editor> renders -- not from its `beforeMount`,
 * which fires only once the loader has already resolved monaco from wherever
 * it was going to get it. That mistake looks like it works: the editor appears
 * and behaves, and the only evidence is a dozen requests to jsdelivr in the
 * network panel. Importing this module for its side effect is what makes the
 * ordering guaranteed.
 */
let configured = false;

export function setupMonaco(): typeof monaco {
  if (configured) return monaco;
  configured = true;

  loader.config({ monaco });

  // One generic worker. The language-specific ones (ts, css, html, json)
  // exist to *edit* those languages; this app shows C, C++, Java and JSON
  // payloads, and json's worker only adds schema validation nobody asked for.
  self.MonacoEnvironment = {
    getWorker: () => new Worker(new URL("./monaco.worker.ts", import.meta.url), { type: "module" }),
  };

  return monaco;
}

// At import time, not at mount time. Both editor components import this module,
// and both are behind `dynamic(..., { ssr: false })`, so it runs in the browser
// exactly once and always before an editor is created.
setupMonaco();
