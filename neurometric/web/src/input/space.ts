// Task space: every task is laid out on a 1280 x 800 CSS-px canvas (battery.CANVAS). The canvas
// is scaled to the viewport; events are recorded in task-space coordinates.
export const TASK_W = 1280;
export const TASK_H = 800;

export interface Rect {
  x: number; // centre
  y: number;
  w: number;
  h: number;
}

export function inside(r: Rect, x: number, y: number): boolean {
  return Math.abs(x - r.x) <= r.w / 2 && Math.abs(y - r.y) <= r.h / 2;
}

export function insideCircle(cx: number, cy: number, w: number, x: number, y: number): boolean {
  return Math.hypot(x - cx, y - cy) <= w / 2;
}
