// Gamepad API adapter: joystick -> cursor velocity (rate control), button -> select.
// Pads are hidden until a "gamepad user gesture"; the adapter polls on requestAnimationFrame
// (the API has no events for axis changes). Gamepad.timestamp is used for sample times when it
// advances, otherwise the frame time.

import type { EventRecorder, StreamHandle } from "./recorder";
import { TASK_H, TASK_W } from "./space";

export interface GamepadConfig {
  deadzone: number; // 0..1
  maxSpeed: number; // task px/s at full deflection
  exponent: number; // response curve (1 linear, 2 quadratic)
  selectButton: number; // standard mapping: 0 = A / cross
  stepButtons: number[]; // e.g. d-pad for scanning
}

export const DEFAULT_GAMEPAD: GamepadConfig = { deadzone: 0.15, maxSpeed: 600, exponent: 2, selectButton: 0, stepButtons: [12, 13, 14, 15] };

/** Map one axis value to a signed speed in px/s (exported for unit tests). */
export function axisToSpeed(a: number, cfg: GamepadConfig): number {
  const m = Math.abs(a);
  if (m <= cfg.deadzone) return 0;
  const n = Math.min(1, (m - cfg.deadzone) / (1 - cfg.deadzone));
  return Math.sign(a) * cfg.maxSpeed * Math.pow(n, cfg.exponent);
}

export interface GamepadAdapterOptions {
  recorder: EventRecorder;
  cfg?: GamepadConfig;
  start?: { x: number; y: number };
  onCursor?: (x: number, y: number, t: number) => void;
  onSelect?: (x: number, y: number, t: number, stream: StreamHandle) => void;
  onStep?: (button: number, t: number) => void;
}

export class GamepadAdapter {
  private raf = 0;
  private prevButtons: boolean[] = [];
  private lastT: number | null = null;
  x: number;
  y: number;
  readonly stream: StreamHandle;
  connected = false;

  constructor(private o: GamepadAdapterOptions) {
    this.x = o.start?.x ?? TASK_W / 2;
    this.y = o.start?.y ?? TASK_H / 2;
    this.stream = o.recorder.stream("in:gamepad", "gamepad");
  }

  start(): void {
    const cfg = this.o.cfg ?? DEFAULT_GAMEPAD;
    const loop = () => {
      this.raf = requestAnimationFrame(loop);
      const pads = typeof navigator.getGamepads === "function" ? navigator.getGamepads() : [];
      const gp = [...pads].find((p) => p && p.connected);
      if (!gp) {
        this.connected = false;
        this.lastT = null;
        return;
      }
      this.connected = true;
      const t = this.o.recorder.clock.now();
      const dt = this.lastT === null ? 0 : Math.min(100, t - this.lastT) / 1000;
      this.lastT = t;
      if (this.o.recorder.paused) return;
      const vx = axisToSpeed(gp.axes[0] ?? 0, cfg);
      const vy = axisToSpeed(gp.axes[1] ?? 0, cfg);
      if ((vx || vy) && dt > 0) {
        this.x = Math.min(TASK_W, Math.max(0, this.x + vx * dt));
        this.y = Math.min(TASK_H, Math.max(0, this.y + vy * dt));
        this.stream.emit({ kind: "pointer_move", x: this.x, y: this.y }, { t });
        this.o.onCursor?.(this.x, this.y, t);
      }
      gp.buttons.forEach((b, i) => {
        const was = this.prevButtons[i] ?? false;
        if (b.pressed && !was) {
          if (i === cfg.selectButton) this.o.onSelect?.(this.x, this.y, t, this.stream);
          else if (cfg.stepButtons.includes(i)) this.o.onStep?.(i, t);
        }
        this.prevButtons[i] = b.pressed;
      });
    };
    this.raf = requestAnimationFrame(loop);
  }

  stop(): void {
    cancelAnimationFrame(this.raf);
  }
}
