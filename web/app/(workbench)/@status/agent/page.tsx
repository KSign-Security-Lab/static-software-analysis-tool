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
 *
 * The structure overlay is rendered by `RunBar` rather than mounted beside it
 * here. It briefly was a sibling, with a provider around the pair of them owning
 * the one 검사 실행 both of them offer -- and a hook that throws when its
 * provider is missing, in a *route* module, is a hook that takes the whole strip
 * down whenever the dev server reloads one of the two and not the other. The
 * button and the drawing it opens are one thing; a prop is enough.
 */
export default function Slot() {
  return <RunBar />;
}
