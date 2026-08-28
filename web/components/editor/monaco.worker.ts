/**
 * The editor's web worker, as a local entry point.
 *
 * It exists only so the bundler has a *relative* module to resolve:
 * `new URL(...)` cannot take a bare package specifier, so pointing a Worker
 * straight at monaco's own file fails to build. One import, and the URL in
 * monaco-setup.ts is relative.
 *
 * Note the short specifier. monaco's `exports` map rewrites `./*` to
 * `./esm/vs/*.js`, so the on-disk path -- `monaco-editor/esm/vs/editor/...` --
 * resolves to `esm/vs/esm/vs/...` and does not exist.
 */
import "monaco-editor/editor/editor.worker.js";
