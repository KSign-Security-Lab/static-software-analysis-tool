import ProblemsDock from "@/features/agent/ProblemsDock";

/**
 * Rendered for both /agent and /agent/trace.
 *
 * Two explicit pages rather than one optional catch-all: a `[[...rest]]` in a
 * parallel slot has the same specificity as the sibling slot's `/agent`, and
 * Next refuses to build. Both render the same element at the same position, so
 * React reconciles it across the switch and nothing remounts.
 */
export default function Slot() {
  return <ProblemsDock />;
}
