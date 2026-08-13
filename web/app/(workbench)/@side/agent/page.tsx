import ExplorerPane from "@/features/agent/ExplorerPane";

/**
 * The file tree, beside both centre views.
 *
 * There used to be a second copy of this page under `agent/trace`, because a
 * `[[...rest]]` in a parallel slot has the same specificity as the sibling
 * slot's `/agent` and Next refuses to build. One surface, one slot now.
 */
export default function Slot() {
  return <ExplorerPane />;
}
