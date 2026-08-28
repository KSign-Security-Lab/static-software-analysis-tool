import Scoreboard from "@/features/bench/Scoreboard";

/**
 * The centre: the number, and everything that has to be true for it to be one.
 *
 * Small and in the corner. The list of failures beside it is the page -- a
 * score rendered large at the top makes every conversation about the score,
 * and the taxonomy underneath it is the only part anyone can act on.
 */
export default function Page() {
  return <Scoreboard />;
}
