/**
 * The JSON language service's worker, as a local entry point.
 *
 * Separate from the editor worker because Monaco routes by label and the
 * generic worker has none of these handlers: a model whose language is `json`
 * asks its worker for `doValidation`, `findDocumentSymbols`, `findDocumentColors`
 * and `getFoldingRanges` unprompted, and answering all four with "missing
 * requestHandler" throws uncaught into the console. The replay diff is JSON, so
 * this is not hypothetical.
 *
 * Same short-specifier reason as monaco.worker.ts: `./*` maps to `./esm/vs/*.js`.
 */
import "monaco-editor/language/json/json.worker.js";
