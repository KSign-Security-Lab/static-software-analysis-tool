import StructureOverlay from "@/features/trace/StructureOverlay";

/**
 * No strip. Only the overlay, which portals to the body and so is drawn nowhere
 * near here -- it is mounted in this slot because the slot renders once for
 * 검사 and only for 검사, which is exactly the lifetime it wants.
 *
 * The strip that used to be here is dissected across the surface: which run and
 * 검사 실행 are the navigator's header and footer, progress is the list moving,
 * and the cost is the right column's. Nothing about a run wanted to be a
 * permanent row.
 */
export default function Slot() {
  return <StructureOverlay />;
}
