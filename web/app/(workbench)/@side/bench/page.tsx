import Instances from "@/features/bench/Instances";

/**
 * The left column: which dataset, then what broke and where.
 *
 * Grouped by failure stage rather than sorted by score, which is the whole
 * ordering argument of this surface.
 */
export default function Slot() {
  return <Instances />;
}
