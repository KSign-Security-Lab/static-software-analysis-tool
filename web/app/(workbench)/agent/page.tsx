import EditorPane from "@/features/agent/EditorPane";

/**
 * The centre: the code, and only the code.
 *
 * It has been a tab strip over four views, an editor split with the finding
 * detail underneath, and an editor with a full-window overlay dropped over it.
 * The overlay was the worst of the three, because it covered the thing every
 * other pane is talking about.
 *
 * Everything else is a pane now -- files left, 상세 right, and the problems, the
 * pipeline, the call record and the state as tabs across the bottom. The reader
 * never leaves the editor to look at any of them.
 */
export default function AgentPage() {
  return <EditorPane />;
}
