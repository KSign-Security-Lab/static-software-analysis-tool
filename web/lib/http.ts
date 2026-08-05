/**
 * Compatibility shim.
 *
 * The transport moved to lib/api/client.ts when the clients were split by
 * resource. The studio components still import from here and are ported one
 * surface at a time; this re-export keeps them on the same implementation
 * meanwhile, so there is never a second base-URL resolution or a second way of
 * wording the same failure.
 *
 * Goes away with the last of those components.
 */
export { ApiError, apiBase, del, get, post, postForm, put, streamUrl } from "./api/client";
