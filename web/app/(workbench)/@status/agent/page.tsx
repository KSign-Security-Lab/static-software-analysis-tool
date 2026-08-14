import RunBar from "@/features/agent/RunBar";

/**
 * One strip, not two.
 *
 * A second row of chips used to sit under this naming every active narrowing.
 * The reader could not tell what the chips were or what removing one would do,
 * and under the current rule they were redundant anyway: the editor's header
 * names the open file and 상세's header names the selection. What only the strip
 * said -- that a run was reopened from this tab's memory -- is a sentence in the
 * bar itself now.
 */
export default function Slot() {
  return <RunBar />;
}
