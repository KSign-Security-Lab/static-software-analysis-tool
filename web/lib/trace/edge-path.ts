/**
 * A polyline drawn with rounded corners.
 *
 * dagre routes every edge while it lays the graph out: it inserts a dummy node per
 * rank an edge crosses, and the points it hands back are a path through the gaps
 * between the real nodes. That routing was being thrown away. Edges were drawn
 * `smoothstep` between fixed handles instead, which knows nothing about what lies
 * between its ends -- so two edges that skipped a rank were both put in the same
 * hand-picked lane and sat on top of each other, and five edges into one node all
 * arrived at a single point.
 *
 * Corners are rounded rather than mitred because a right angle at every bend reads
 * as a circuit diagram, and the radius is clamped to half the shorter segment so a
 * tight bend degenerates to a corner instead of overshooting into the segment
 * before it.
 */

export interface Point {
  x: number;
  y: number;
}

/** Default corner radius. Enough to read as a turn, small enough to stay a line. */
export const CORNER = 10;

function distance(from: Point, to: Point): number {
  return Math.hypot(to.x - from.x, to.y - from.y);
}

/** The point `by` along the way from `from` to `to`. */
function towards(from: Point, to: Point, by: number): Point {
  const span = distance(from, to);
  if (span === 0) return { ...from };
  const ratio = Math.min(1, by / span);
  return { x: from.x + (to.x - from.x) * ratio, y: from.y + (to.y - from.y) * ratio };
}

function round(value: number): number {
  // One decimal: an SVG path does not need more, and the attribute is re-serialised
  // on every render.
  return Math.round(value * 10) / 10;
}

/**
 * An SVG path through `points`, with each bend eased.
 *
 * Consecutive duplicate points are dropped: dagre emits them where a route enters
 * and leaves a dummy node at the same coordinate, and a zero-length segment turns
 * the corner maths into a division by zero.
 */
export function roundedPath(points: Point[], radius = CORNER): string {
  const path: Point[] = [];
  for (const point of points) {
    const last = path[path.length - 1];
    if (!last || last.x !== point.x || last.y !== point.y) path.push(point);
  }
  if (path.length === 0) return "";
  if (path.length === 1) return `M ${round(path[0].x)},${round(path[0].y)}`;

  let out = `M ${round(path[0].x)},${round(path[0].y)}`;
  for (let index = 1; index < path.length - 1; index += 1) {
    const previous = path[index - 1];
    const corner = path[index];
    const next = path[index + 1];
    // Half the shorter segment, so two bends close together cannot eat past each
    // other and cross the line they are meant to be smoothing.
    const limit = Math.min(radius, distance(previous, corner) / 2, distance(corner, next) / 2);
    const enter = towards(corner, previous, limit);
    const leave = towards(corner, next, limit);
    out += ` L ${round(enter.x)},${round(enter.y)} Q ${round(corner.x)},${round(corner.y)} ${round(leave.x)},${round(leave.y)}`;
  }
  const end = path[path.length - 1];
  return `${out} L ${round(end.x)},${round(end.y)}`;
}
