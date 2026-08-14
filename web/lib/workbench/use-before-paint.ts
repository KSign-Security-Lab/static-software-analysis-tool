"use client";

import { useEffect, useLayoutEffect } from "react";

/**
 * `useLayoutEffect`, except on the server.
 *
 * Panel folds have to be applied after commit and before the browser paints, or
 * the reader sees the un-folded layout for a frame and watches it collapse. That
 * is `useLayoutEffect` -- which warns when React renders a client component on
 * the server, as Next does for every one of these.
 *
 * Defined once because there are two callers who must not drift: the shell folds
 * side/dock/inspector from a cookie, and `CentrePane` folds the finding panel
 * from `?finding=`. Both are "the correct layout on the first frame the reader
 * sees", and both are wrong in exactly the same visible way if they use a plain
 * effect.
 */
export const useBeforePaint = typeof window === "undefined" ? useEffect : useLayoutEffect;
