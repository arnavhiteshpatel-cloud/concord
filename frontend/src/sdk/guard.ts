// BrainOS TypeScript SDK — command-safety helper for applications that act on commands.
// Same behaviour as the Python SDK's CommandGuard (backend/src/brainos/sdk/guard.py):
//
//   const guard = new CommandGuard({ onStop: (why) => showStopped(why) });
//   const detach = attachGuard(stream, guard, (e) => act(e));   // only fresh, usable commands
//   guard.waitingForAuthorization   // e.g. ["selection"] until the operator authorizes the app
//   guard.velocity                  // last fresh pointer velocity, or zero (dead-man / stopped)
//
// It never talks to the runtime: authorization is the operator's decision.

import type { BrainOSStream, ConnectionStatus } from "./client";
import type { Capability, EventEnvelope, NegotiationResult, RuntimeSnapshot } from "./types";

export type CommandCapability = "pointer_intent" | "selection" | "text_intent";
export const COMMAND_CAPABILITIES: readonly CommandCapability[] = ["pointer_intent", "selection", "text_intent"];
const COMMAND_EVENTS: Record<string, CommandCapability> = {
  "intent.pointer": "pointer_intent",
  "intent.selection": "selection",
  "intent.text": "text_intent",
};

export const DEFAULT_MAX_AGE_MS = 500;
export const DEFAULT_DEADMAN_MS = 500;

export interface GuardOptions {
  capabilities?: CommandCapability[];
  /** drop commands older than this (wall clock and relative delivery delay) */
  maxAgeMs?: number;
  /** no pointer command for this long => velocity reported as zero */
  deadmanMs?: number;
  /** compare envelope timestamps with the local wall clock (off when the runtime is remote) */
  compareWallClock?: boolean;
  onStop?: (reason: string) => void;
  onDeadman?: () => void;
  /** clocks, injectable for tests: wall clock in ms since epoch, monotonic ms */
  wallMs?: () => number;
  monoMs?: () => number;
}

export interface GuardStats {
  accepted: number;
  droppedInactive: number;
  droppedStale: number;
  droppedLate: number;
  stops: number;
  deadman: number;
}

/** Why a capability is not usable: "" when negotiation grants it. */
type Negotiated = "" | "connecting" | "not_authorized" | "unavailable" | "no_device" | "suspended";

export class CommandGuard {
  readonly capabilities: CommandCapability[];
  readonly stats: GuardStats = { accepted: 0, droppedInactive: 0, droppedStale: 0, droppedLate: 0, stops: 0, deadman: 0 };
  stopReason: string | null = null;
  private negotiated = new Map<CommandCapability, Negotiated>();
  private source = "unknown";
  private session: string | null = null;
  private closed = false;
  private activeSet = new Set<CommandCapability>();
  private minOffsetMs: number | null = null;
  private lastPointerMs: number | null = null;
  private vel: [number, number] = [0, 0];
  private idle = true;
  private readonly maxAgeMs: number;
  private readonly deadmanMs: number;
  private readonly compareWallClock: boolean;
  private readonly wallMs: () => number;
  private readonly monoMs: () => number;

  constructor(private readonly opts: GuardOptions = {}) {
    this.capabilities = [...new Set(opts.capabilities ?? COMMAND_CAPABILITIES)];
    this.maxAgeMs = opts.maxAgeMs ?? DEFAULT_MAX_AGE_MS;
    this.deadmanMs = opts.deadmanMs ?? DEFAULT_DEADMAN_MS;
    if (!(this.maxAgeMs > 0) || !(this.deadmanMs > 0)) throw new Error("maxAgeMs and deadmanMs must be positive");
    this.compareWallClock = opts.compareWallClock ?? true;
    this.wallMs = opts.wallMs ?? (() => Date.now());
    this.monoMs = opts.monoMs ?? (() => performance.now());
    for (const c of this.capabilities) this.negotiated.set(c, "connecting");
  }

  isActive(c: CommandCapability): boolean {
    return this.activeSet.has(c);
  }

  get active(): CommandCapability[] {
    return [...this.activeSet];
  }

  /** "active" or why not: not_authorized, unavailable, no_device, suspended, source_<state>, closed, … */
  state(c: CommandCapability): string {
    const n = this.negotiated.get(c);
    if (n === undefined) return "not_requested";
    if (this.activeSet.has(c)) return "active";
    if (this.closed) return "closed";
    return n || `source_${this.source}`;
  }

  get waitingForAuthorization(): CommandCapability[] {
    return this.capabilities.filter((c) => this.negotiated.get(c) === "not_authorized");
  }

  get velocity(): [number, number] {
    return this.activeSet.has("pointer_intent") && !this.idle ? [this.vel[0], this.vel[1]] : [0, 0];
  }

  onNegotiation(n: NegotiationResult): void {
    const granted = new Set<Capability>(n.granted);
    const rejected = new Map(n.rejected.map((r) => [r.capability, r.reason] as const));
    for (const c of this.capabilities) {
      if (granted.has(c)) this.negotiated.set(c, "");
      else if (rejected.has(c)) {
        const r = rejected.get(c);
        this.negotiated.set(c, r === "not_authorized" ? "not_authorized" : r === "no_device" ? "no_device" : "unavailable");
      } else this.negotiated.set(c, n.status === "no_device" ? "no_device" : "suspended");
    }
    this.update();
  }

  onRuntime(r: Pick<RuntimeSnapshot, "state" | "session_id">): void {
    if (r.session_id !== this.session) {
      this.session = r.session_id;
      this.minOffsetMs = null;
      this.lastPointerMs = null;
    }
    this.source = r.state;
    this.update();
  }

  onConnection(status: ConnectionStatus): void {
    if (status === "open") {
      this.closed = false;
      this.update();
    } else if (status !== "connecting") {
      this.closed = true;
      this.update(status === "reconnecting" ? "connection lost" : "stream closed");
    }
  }

  /** True if the app should act on this command now. Non-command events return false. */
  accept(e: EventEnvelope): boolean {
    const cap = COMMAND_EVENTS[e.event_type];
    if (!cap) return false;
    if (!this.activeSet.has(cap)) {
      this.stats.droppedInactive += 1;
      return false;
    }
    const tsMs = e.timestamp_ns / 1e6;
    if (this.compareWallClock && this.wallMs() - tsMs > this.maxAgeMs) {
      this.stats.droppedStale += 1;
      return false;
    }
    const now = this.monoMs();
    const offset = now - tsMs;
    if (this.minOffsetMs === null || offset < this.minOffsetMs) this.minOffsetMs = offset;
    if (offset - this.minOffsetMs > this.maxAgeMs) {
      this.stats.droppedLate += 1;
      return false;
    }
    this.stats.accepted += 1;
    if (cap === "pointer_intent" && e.event_type === "intent.pointer") {
      this.vel = [e.payload.vx, e.payload.vy];
      this.lastPointerMs = now;
      this.idle = false;
    }
    return true;
  }

  /** Dead-man check; call every few tens of ms. Returns true when it just fired. */
  tick(): boolean {
    if (this.idle || this.lastPointerMs === null) return false;
    if (this.monoMs() - this.lastPointerMs <= this.deadmanMs) return false;
    this.idle = true;
    this.stats.deadman += 1;
    this.opts.onDeadman?.();
    return true;
  }

  private update(reason?: string): void {
    const streaming = this.source === "streaming" || this.source === "unknown";
    const next = new Set(this.capabilities.filter((c) => !this.closed && streaming && this.negotiated.get(c) === ""));
    const lost = [...this.activeSet].filter((c) => !next.has(c)).sort();
    this.activeSet = next;
    if (lost.length) {
      const why = reason ?? this.why(lost[0]!);
      this.stopReason = why;
      this.stats.stops += 1;
      this.vel = [0, 0];
      this.idle = true;
      this.lastPointerMs = null;
      this.opts.onStop?.(why);
    } else if (next.size) this.stopReason = null;
  }

  private why(c: CommandCapability): string {
    switch (this.negotiated.get(c)) {
      case "not_authorized":
        return "authorization revoked";
      case "unavailable":
        return "command output stopped";
      case "no_device":
        return "source disconnected";
      case "suspended":
        return "application suspended";
      default:
        return `source ${this.source}`;
    }
  }
}

/** Wire a guard to a stream: negotiation/runtime/connection updates, the dead-man timer, and a
 *  callback for fresh, usable commands only. Returns a function that detaches everything. */
export function attachGuard(
  stream: BrainOSStream,
  guard: CommandGuard,
  onCommand: (e: EventEnvelope) => void,
  tickMs = 20,
): () => void {
  if (stream.negotiation) guard.onNegotiation(stream.negotiation);
  if (stream.runtime) guard.onRuntime(stream.runtime);
  const off = [
    stream.on("negotiation", (n) => guard.onNegotiation(n)),
    stream.on("runtime", (r) => guard.onRuntime(r)),
    stream.on("status", (s) => guard.onConnection(s)),
    stream.on("event", (e) => {
      if (guard.accept(e)) onCommand(e);
    }),
  ];
  const timer = setInterval(() => guard.tick(), tickMs);
  return () => {
    clearInterval(timer);
    for (const f of off) f();
  };
}
