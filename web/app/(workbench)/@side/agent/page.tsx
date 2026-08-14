import Navigator from "@/features/agent/Navigator";

/**
 * The left column.
 *
 * It was the file tree and nothing else, while a 36px strip across the top of
 * the window carried which run was open, how far it had got, and the button
 * that fills it. Those are all facts about what this column lists, so they are
 * its header, its progress line and its footer now -- and the strip is gone.
 */
export default function Slot() {
  return <Navigator />;
}
