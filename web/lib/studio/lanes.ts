import type { Checkpoint } from "@/lib/api/studio";

/**
 * Reading a thread's history as a tree.
 *
 * A history is a straight line until somebody writes over an old step. That
 * write records the old step as its parent, so a second child of any step is a
 * second line -- which is what a fork is, and the only thing it can be drawn
 * from.
 */

/**
 * Assign each checkpoint a lane. Lane 0 is the course the run originally took.
 */
export function lanesOf(checkpoints: Checkpoint[]): Map<string, number> {
  const lanes = new Map<string, number>();
  const childrenSeen = new Map<string, number>();
  let nextLane = 0;

  for (const point of checkpoints) {
    const id = point.checkpoint_id;
    if (!id) continue;
    const parent = point.parent_checkpoint_id;

    if (!parent || !lanes.has(parent)) {
      lanes.set(id, parent ? nextLane : 0);
      if (parent) nextLane += 1;
      continue;
    }

    const older = childrenSeen.get(parent) ?? 0;
    childrenSeen.set(parent, older + 1);
    // The first child continues its parent's line; any later one starts a new
    // one, which is exactly what a fork is.
    lanes.set(id, older === 0 ? (lanes.get(parent) ?? 0) : (nextLane += 1));
  }

  return lanes;
}

/**
 * The state keys one step changed.
 *
 * The thread history is about what each node *did*, not about the whole state
 * carried forward -- most of which the node never touched. Compared against the
 * parent rather than the previous row, so a fork is compared with the step it
 * actually came from.
 */
export function changedKeys(step: Checkpoint, parent: Checkpoint | undefined): string[] {
  const before = parent?.values ?? {};
  const after = step.values ?? {};

  return Object.keys(after).filter((key) => {
    if (!(key in before)) return true;
    return JSON.stringify(before[key]) !== JSON.stringify(after[key]);
  });
}

/** Index a history by checkpoint id, for parent lookups. */
export function byId(checkpoints: Checkpoint[]): Map<string, Checkpoint> {
  return new Map(checkpoints.filter((c) => c.checkpoint_id).map((c) => [c.checkpoint_id as string, c]));
}
