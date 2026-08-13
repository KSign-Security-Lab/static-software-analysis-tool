import CodePane from "@/features/inspect/CodePane";

/**
 * 검사: the code, with the problems in it.
 *
 * The centre is the editor and nothing else. It used to be four tabs -- the code,
 * the agent's structure, the code's own graph, and a dump of the run's state --
 * of which one is what you came here to look at and three are about the checker.
 * Those three live under /agent/machine now.
 */
export default function AgentPage() {
  return <CodePane />;
}
