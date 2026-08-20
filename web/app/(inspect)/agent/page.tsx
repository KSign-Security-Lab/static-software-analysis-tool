import Inspect from "@/features/inspect/Inspect";

/**
 * 검사.
 *
 * One route for all three stages -- intake, scanning, results -- because they
 * are one flow over one run, and the stage is derived from the run's own state
 * rather than stored. See `lib/inspect/stage.ts`: a stage held in React would be
 * a second source of truth next to the run status, and the two would disagree
 * exactly when it mattered.
 */
export default function AgentPage() {
  return <Inspect />;
}
