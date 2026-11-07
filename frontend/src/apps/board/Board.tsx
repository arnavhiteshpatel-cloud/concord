// Communication Board — a demonstration application.
// It is controlled ONLY through BrainOS runtime events (no mouse/keyboard input),
// imports ONLY from src/sdk, and contains no device-specific code.

import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  BrainOSStream,
  type ConnectionStatus,
  type EventEnvelope,
  type ProvenanceKind,
} from "../../sdk";
import { COLS, TILES, boardReducer, initialBoard, type BoardState } from "./model";

const SCAN_INTERVAL_MS = 1100;

const MODE_LABEL: Record<BoardState["mode"], string> = {
  pointer: "Pointer mode",
  scan: "Scan mode",
  inactive: "Waiting",
};

const MODE_TEXT: Record<BoardState["mode"], string> = {
  pointer: "Move the cursor to a phrase, then select it.",
  scan: "Phrases are highlighted in turn. Select when the one you want is highlighted.",
  inactive: "Waiting for a source that can make a selection.",
};

const CONN_TEXT: Record<ConnectionStatus, string> = {
  idle: "Not connected",
  connecting: "Connecting",
  open: "Connected to BrainOS",
  reconnecting: "Reconnecting",
  closed: "Disconnected",
  rejected: "Connection refused",
};

const INPUT_TEXT: Partial<Record<ProvenanceKind, string>> = {
  simulated_intent: "simulated",
  decoded_intent: "decoded by a model",
};

const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? "" : "s"}`;

export function Board({ streamUrl }: { streamUrl?: string }) {
  const [state, dispatch] = useReducer(boardReducer, undefined, initialBoard);
  const [conn, setConn] = useState<ConnectionStatus>("idle");
  const [lastKind, setLastKind] = useState<ProvenanceKind | null>(null);
  const [device, setDevice] = useState<string | null>(null);
  const [stats, setStats] = useState({ received: 0, deliveryGaps: 0 });
  const [flash, setFlash] = useState<number | null>(null);
  const streamRef = useRef<BrainOSStream | null>(null);

  useEffect(() => {
    const stream = new BrainOSStream({
      app: { id: "communication-board", name: "Communication Board" },
      required: ["selection"],
      optional: ["pointer_intent", "text_intent"],
      url: streamUrl,
    });
    streamRef.current = stream;
    const offs = [
      stream.on("status", setConn),
      stream.on("negotiation", (n) => {
        setDevice(n.device_id);
        dispatch({ type: "negotiation", negotiation: n });
      }),
      stream.on("event", (e: EventEnvelope) => {
        switch (e.event_type) {
          case "intent.pointer":
            dispatch({ type: "pointer", ...e.payload, timestampNs: e.timestamp_ns });
            break;
          case "intent.selection":
            dispatch({ type: "select" });
            setLastKind(e.provenance.kind);
            break;
          case "intent.text":
            dispatch({ type: "text", text: e.payload.text, mode: e.payload.mode });
            setLastKind(e.provenance.kind);
            break;
          default:
            break;
        }
      }),
    ];
    stream.connect();
    const statTimer = setInterval(() => {
      setStats({ received: stream.stats.received, deliveryGaps: stream.stats.deliveryGaps });
    }, 500);
    return () => {
      offs.forEach((off) => off());
      clearInterval(statTimer);
      stream.close();
    };
  }, [streamUrl]);

  useEffect(() => {
    if (state.mode !== "scan") return;
    const t = setInterval(() => dispatch({ type: "scanTick" }), SCAN_INTERVAL_MS);
    return () => clearInterval(t);
  }, [state.mode]);

  useEffect(() => {
    if (!state.lastSelected) return;
    setFlash(state.lastSelected.index);
    const t = setTimeout(() => setFlash(null), 350);
    return () => clearTimeout(t);
  }, [state.lastSelected]);

  const speechAvailable = typeof window !== "undefined" && "speechSynthesis" in window;
  useEffect(() => {
    if (state.speakRequests === 0 || !speechAvailable || !state.message.trim()) return;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(state.message));
  }, [state.speakRequests]);

  const active = state.mode === "pointer" ? state.hover : state.mode === "scan" ? state.scanIndex : null;
  const textEnabled = state.granted.includes("text_intent");
  const rows = useMemo(() => Math.ceil(TILES.length / COLS), []);

  return (
    <div className="board" data-mode={state.mode}>
      <header className="board-head">
        <span className="board-name">Communication board</span>
        <span className="board-tag">Research use only</span>
        <span className="board-status" aria-live="polite">
          <span className={`dot dot-${state.mode}`} aria-hidden />
          <span data-testid="board-mode" data-mode={state.mode}>
            {MODE_LABEL[state.mode]}
          </span>
        </span>
        <span className="board-spacer" />
        <span className={`board-conn conn-${conn}`} data-testid="board-conn" data-conn={conn}>
          {CONN_TEXT[conn] ?? conn}
        </span>
      </header>

      <div className="board-message" aria-live="polite" data-testid="board-message">
        {state.message || <span className="placeholder">Message appears here…</span>}
        {textEnabled && <span className="caret" aria-hidden />}
      </div>

      <div className="board-hint">{MODE_TEXT[state.mode]}</div>

      <div
        className="board-grid"
        style={{ gridTemplateColumns: `repeat(${COLS}, 1fr)`, gridTemplateRows: `repeat(${rows}, 1fr)` }}
        role="grid"
        aria-label="phrases"
      >
        {TILES.map((tile, i) => (
          <div
            key={tile.label}
            role="gridcell"
            data-testid={`tile-${i}`}
            data-active={active === i ? "true" : "false"}
            aria-selected={active === i}
            className={[
              "tile",
              `tile-${tile.kind}`,
              active === i ? "tile-active" : "",
              flash === i ? "tile-flash" : "",
              tile.kind === "speak" && !speechAvailable ? "tile-disabled" : "",
            ].join(" ")}
          >
            {tile.label}
            {tile.kind === "speak" && !speechAvailable && <small>speech unavailable</small>}
          </div>
        ))}
        {state.mode === "pointer" && (
          <div
            className="cursor"
            data-testid="board-cursor"
            style={{ left: `${state.cursor.x * 100}%`, top: `${state.cursor.y * 100}%` }}
          />
        )}
      </div>

      <footer className="board-foot">
        <span>
          {lastKind ? `Last input: ${INPUT_TEXT[lastKind] ?? lastKind.replace("_", " ")}` : "No input yet"}
          {device ? ` · source ${device}` : ""}
        </span>
        <span data-testid="board-stats">
          {plural(state.selections, "selection")} · {plural(stats.received, "event")} · {plural(stats.deliveryGaps, "delivery gap")}
        </span>
      </footer>
    </div>
  );
}
