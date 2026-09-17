export interface Point {
  x: number;
  y: number;
}

export const CORNER = 10;

function distance(from: Point, to: Point): number {
  return Math.hypot(to.x - from.x, to.y - from.y);
}

function towards(from: Point, to: Point, by: number): Point {
  const span = distance(from, to);
  if (span === 0) return { ...from };
  const ratio = Math.min(1, by / span);
  return { x: from.x + (to.x - from.x) * ratio, y: from.y + (to.y - from.y) * ratio };
}

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

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
    const limit = Math.min(radius, distance(previous, corner) / 2, distance(corner, next) / 2);
    const enter = towards(corner, previous, limit);
    const leave = towards(corner, next, limit);
    out += ` L ${round(enter.x)},${round(enter.y)} Q ${round(corner.x)},${round(corner.y)} ${round(leave.x)},${round(leave.y)}`;
  }
  const end = path[path.length - 1];
  return `${out} L ${round(end.x)},${round(end.y)}`;
}
