// BrainOS TypeScript SDK — stream client.
//
//   const stream = new BrainOSStream({
//     app: { id: "my-app", name: "My App" },
//     required: ["selection"],
//     optional: ["pointer_intent"],
//   });
//   stream.on("negotiation", (n) => ...);   // adapt to granted capabilities
//   stream.on("event", (e) => ...);         // validated EventEnvelope
//   stream.connect();

import { validateEnvelope } from "./validate";
import {
  STREAM_PROTOCOL,
  type AppInfo,
  type Capability,
  type EventEnvelope,
  type NegotiationResult,
  type RuntimeSnapshot,
  type ServerMessage,
} from "./types";

export type ConnectionStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed" | "rejected";

export interface StreamStats {
  received: number;
  invalid: number;
  deliveryGaps: number;
  missedEvents: number;
  outOfOrder: number;
  connections: number;
}

/** Tracks delivery_seq contiguity (server drops) and per-session seq ordering. Pure. */
export class StreamTracker {
  stats: StreamStats = {
    received: 0,
    invalid: 0,
    deliveryGaps: 0,
    missedEvents: 0,
    outOfOrder: 0,
    connections: 0,
  };
  private lastDelivery: number | null = null;
  private lastSeq = new Map<string, number>();

  newConnection(): void {
    this.lastDelivery = null; // delivery_seq restarts per connection
    this.stats.connections += 1;
  }

  observe(deliverySeq: number, env: EventEnvelope | null): void {
    if (this.lastDelivery !== null && deliverySeq !== this.lastDelivery + 1) {
      this.stats.deliveryGaps += 1;
      this.stats.missedEvents += Math.max(0, deliverySeq - this.lastDelivery - 1);
    }
    this.lastDelivery = deliverySeq;
    if (!env) {
      this.stats.invalid += 1;
      return;
    }
    this.stats.received += 1;
    const last = this.lastSeq.get(env.session_id);
    if (last !== undefined && env.seq <= last) this.stats.outOfOrder += 1;
    this.lastSeq.set(env.session_id, env.seq);
  }
}

export interface StreamOptions {
  app: AppInfo;
  required: Capability[];
  optional?: Capability[];
  /** Full ws:// URL. Defaults to the current page's host + /api/v1/stream. */
  url?: string;
  /** Reconnect automatically when the connection drops (default true). */
  reconnect?: boolean;
  /** Factory for tests. */
  webSocket?: (url: string) => WebSocket;
}

export interface StreamListeners {
  event: (e: EventEnvelope) => void;
  negotiation: (n: NegotiationResult) => void;
  runtime: (r: RuntimeSnapshot) => void;
  status: (s: ConnectionStatus) => void;
  notice: (n: { code: string; message: string }) => void;
}

type ListenerSets = { [K in keyof StreamListeners]: Set<StreamListeners[K]> };

const BACKOFF_MS = [250, 500, 1000, 2000, 4000];

export function defaultStreamUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/api/v1/stream`;
}

export class BrainOSStream {
  status: ConnectionStatus = "idle";
  negotiation: NegotiationResult | null = null;
  runtime: RuntimeSnapshot | null = null;
  connectionId: string | null = null;
  readonly tracker = new StreamTracker();

  private ws: WebSocket | null = null;
  private attempt = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private closedByUser = false;
  private listeners: ListenerSets = {
    event: new Set(),
    negotiation: new Set(),
    runtime: new Set(),
    status: new Set(),
    notice: new Set(),
  };

  constructor(private readonly opts: StreamOptions) {}

  get stats(): StreamStats {
    return this.tracker.stats;
  }

  get granted(): Capability[] {
    return this.negotiation?.granted ?? [];
  }

  on<K extends keyof StreamListeners>(type: K, fn: StreamListeners[K]): () => void {
    (this.listeners[type] as Set<StreamListeners[K]>).add(fn);
    return () => (this.listeners[type] as Set<StreamListeners[K]>).delete(fn);
  }

  private emit<K extends keyof StreamListeners>(type: K, arg: Parameters<StreamListeners[K]>[0]) {
    for (const fn of this.listeners[type] as Set<(a: typeof arg) => void>) fn(arg);
  }

  private setStatus(s: ConnectionStatus) {
    if (s !== this.status) {
      this.status = s;
      this.emit("status", s);
    }
  }

  connect(): void {
    this.closedByUser = false;
    this.open();
  }

  close(): void {
    this.closedByUser = true;
    if (this.timer) clearTimeout(this.timer);
    this.ws?.close();
    this.ws = null;
    this.setStatus("closed");
  }

  private open(): void {
    const url = this.opts.url ?? defaultStreamUrl();
    this.setStatus(this.attempt === 0 ? "connecting" : "reconnecting");
    const ws = this.opts.webSocket ? this.opts.webSocket(url) : new WebSocket(url);
    this.ws = ws;
    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          type: "hello",
          protocol: STREAM_PROTOCOL,
          app: { kind: "application", ...this.opts.app },
          capabilities: { required: this.opts.required, optional: this.opts.optional ?? [] },
        }),
      );
    };
    ws.onmessage = (m: MessageEvent) => this.handle(String(m.data));
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      if (this.closedByUser || this.status === "rejected" || this.opts.reconnect === false) {
        if (this.status !== "rejected") this.setStatus("closed");
        return;
      }
      const delay = BACKOFF_MS[Math.min(this.attempt, BACKOFF_MS.length - 1)] ?? 4000;
      this.attempt += 1;
      this.setStatus("reconnecting");
      this.timer = setTimeout(() => this.open(), delay);
    };
  }

  /** Handle one raw server frame. Public for tests. */
  handle(raw: string): void {
    let msg: ServerMessage;
    try {
      msg = JSON.parse(raw) as ServerMessage;
    } catch {
      this.emit("notice", { code: "protocol_error", message: "unparseable frame from server" });
      return;
    }
    switch (msg.type) {
      case "welcome":
        this.attempt = 0;
        this.connectionId = msg.connection_id;
        this.tracker.newConnection();
        this.negotiation = msg.negotiation;
        this.runtime = msg.runtime;
        this.setStatus("open");
        this.emit("negotiation", msg.negotiation);
        this.emit("runtime", msg.runtime);
        break;
      case "event": {
        const v = validateEnvelope(msg.event);
        this.tracker.observe(msg.delivery_seq, v.ok ? v.event : null);
        if (v.ok) this.emit("event", v.event);
        else this.emit("notice", { code: "invalid_event", message: v.error });
        break;
      }
      case "negotiation":
        this.negotiation = msg.negotiation;
        this.emit("negotiation", msg.negotiation);
        break;
      case "runtime":
        this.runtime = msg.runtime;
        this.emit("runtime", msg.runtime);
        break;
      case "error":
        if (this.status !== "open") this.setStatus("rejected"); // handshake rejected: do not retry
        this.emit("notice", { code: msg.code, message: msg.message });
        break;
      default:
        break; // pong and unknown future types
    }
  }
}
