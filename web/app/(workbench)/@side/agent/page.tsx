import ExplorerPane from "@/features/agent/ExplorerPane";

/**
 * The file tree, and nothing else.
 *
 * It shared this rail with the 문제 list for a while, which meant the left side
 * had two subjects and the problems had to be folded away to see the files or
 * the other way round. 문제 is the bottom panel now -- where a problems list
 * belongs and where its rows have width -- so this is the explorer, full height.
 */
export default function Slot() {
  return <ExplorerPane />;
}
