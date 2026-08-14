"use client";

import RunList from "./RunList";

/**
 * 실행: what this run did, as one list.
 *
 * The structure used to sit above this and is in the right-hand pane now. It was
 * the wrong neighbour: three regions shared this column -- the code, the drawing,
 * the record -- and all three want height, so whichever one was given enough left
 * the other two squeezed.
 */
export default function RunPanel() {
  return <RunList />;
}
