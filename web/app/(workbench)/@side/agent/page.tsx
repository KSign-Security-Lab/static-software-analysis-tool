import ExplorerPane from "@/features/agent/ExplorerPane";
import FindingRail from "@/features/inspect/FindingRail";

/**
 * The problems, and under them the files they were found in.
 *
 * In that order, because that is the order of the work: you come back to this
 * screen to deal with what the last run found, and you touch the file list when
 * you are adding code or moving to another file. The explorer had the whole rail
 * to itself and the problems were in a shelf along the bottom, which had it
 * exactly the wrong way round.
 */
export default function Slot() {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1">
        <FindingRail />
      </div>
      <div className="flex max-h-[45%] min-h-0 shrink-0 flex-col border-t border-line">
        <ExplorerPane />
      </div>
    </div>
  );
}
