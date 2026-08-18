import CentrePane from "@/features/agent/CentrePane";

/**
 * The centre: the code, or the pipeline that read it.
 *
 * The drawing used to be an overlay, because no pane on a four-pane workbench
 * was big enough for it and there was nowhere else to put it. A tab is where it
 * belongs -- the centre is the widest region on the surface, and a tab needs no
 * portal, no focus trap and no Escape handler.
 */
export default function Page() {
  return <CentrePane />;
}
