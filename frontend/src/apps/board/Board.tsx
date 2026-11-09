// Communication Board v2 — a demonstration application for text communication.
// Controlled ONLY through Concord runtime events (the participant view takes no mouse or
// keyboard input), imports ONLY from src/sdk, and contains no device-specific code. Every
// command passes the SDK CommandGuard first: nothing acts unless the runtime grants it, the
// source streams and the runtime's control.state says command delivery is active.

import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  ConcordStream,
  CommandGuard,
  attachGuard,
  type ConnectionStatus,
  type ControlStateInfo,
  type EventEnvelope,
} from "../../sdk";
import { SPEECH_LABEL, speak, speechAvailable, tick as audioTick } from "./feedback";
import { METHOD_LABEL, methodHint } from "./methods";
import { boardReducer, buildPage, focusTile, initialBoard, scanRow, speakLabel, type BoardState } from "./model";
import { compositionLabel, dataQualifiers, inputLabel, refOf } from "./provenance";
import { loadSettings, saveSettings, type BoardSettings } from "./settings";
import { SettingsPanel } from "./SettingsPanel";
import { exposeSnapshot, snapshot } from "./snapshot";
import { CORE_WORDS, parseWordList } from "./vocabulary";

export const APP_ID = "communication-board";
const TICK_MS = 50;

const CONN_TEXT: Record<ConnectionStatus, string> = {
  idle: "Not connected",
  connecting: "Connecting",
  open: "Connected to Concord",
  reconnecting: "Reconnecting",
  closed: "Disconnected",
  rejected: "Connection refused",
};

const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? "" : "s"}`;
const now = () => performance.now();

export function Board({ streamUrl, search }: { streamUrl?: string; search?: string }) {
  const [state, dispatch] = useReducer(boardReducer, undefined, () =>
    initialBoard(loadSettings(search ?? (typeof window !== "undefined" ? window.location.search : ""))),
  );
  const [conn, setConn] = useState<ConnectionStatus>("idle");
  const [control, setControl] = useState<ControlStateInfo | null>(null);
  const [stats, setStats] = useState({ received: 0, deliveryGaps: 0 });
  const [showSettings, setShowSettings] = useState(false);
  const [wordsError, setWordsError] = useState<string | null>(null);
  const [announce, setAnnounce] = useState("");
  const stateRef = useRef<BoardState>(state);
  stateRef.current = state;
  const extraRef = useRef<{ conn: ConnectionStatus; control: ControlStateInfo | null; guard: CommandGuard | null }>({
    conn: "idle",
    control: null,
    guard: null,
  });
  extraRef.current.conn = conn;
  extraRef.current.control = control;

  // ---------------------------------------------------------------- runtime connection
  useEffect(() => {
    dispatch({ type: "speechAvailable", available: speechAvailable() });
    const stream = new ConcordStream({
      app: { id: APP_ID, name: "Communication Board" },
      // nothing is required: the board adapts to whatever input the runtime grants
      required: [],
      optional: ["pointer_intent", "selection", "navigation", "text_intent", "control_status"],
      url: streamUrl,
    });
    const guard = new CommandGuard({
      capabilities: ["pointer_intent", "selection", "navigation", "text_intent"],
      onControlState: (c) => setControl({ ...c }),
    });
    extraRef.current.guard = guard;
    const usable = () =>
      dispatch({
        type: "usable",
        caps: guard.active,
        // after a loss: the runtime's own reason (control.state) when it has one
        reason: guard.stopReason === null ? null : (guard.controlState?.active === false && guard.controlState.reason) || guard.stopReason,
        waiting: guard.waitingForAuthorization,
      });
    const onCommand = (e: EventEnvelope) => {
      const ref = refOf(e);
      const t = now();
      switch (e.event_type) {
        case "intent.pointer":
          dispatch({ type: "pointer", vx: e.payload.vx, vy: e.payload.vy, ref, nowMs: t });
          break;
        case "intent.selection":
          dispatch({ type: "select", action: e.payload.action, ref, nowMs: t });
          break;
        case "intent.navigate":
          dispatch({ type: "navigate", direction: e.payload.direction, ref, nowMs: t });
          break;
        case "intent.text":
          dispatch({ type: "text", text: e.payload.text, mode: e.payload.mode, ref, nowMs: t });
          break;
        default:
          break;
      }
    };
    // the guard sees every update first; the model then reads what is usable
    const detach = attachGuard(stream, guard, onCommand);
    const offs = [
      stream.on("negotiation", (n) => {
        dispatch({ type: "negotiation", negotiation: n });
        usable();
      }),
      stream.on("runtime", (r) => {
        usable();
        const dev = r && r.state !== "idle" ? r.device : null;
        dispatch({ type: "source", key: dev ? `${dev.device_id}|${r.session_id ?? ""}` : null });
      }),
      stream.on("status", (s) => {
        setConn(s);
        usable();
      }),
      stream.on("event", (e) => {
        if (e.event_type === "control.state") usable();
      }),
    ];
    stream.connect();
    const ticker = setInterval(() => dispatch({ type: "tick", nowMs: now() }), TICK_MS);
    const statTimer = setInterval(() => setStats({ received: stream.stats.received, deliveryGaps: stream.stats.deliveryGaps }), 500);
    const unexpose = exposeSnapshot(() =>
      snapshot(stateRef.current, {
        connection: extraRef.current.conn,
        control: extraRef.current.control,
        guard: extraRef.current.guard ? { ...extraRef.current.guard.stats } : null,
      }),
    );
    return () => {
      offs.forEach((off) => off());
      detach();
      clearInterval(ticker);
      clearInterval(statTimer);
      unexpose();
      stream.close();
    };
  }, [streamUrl]);

  // ---------------------------------------------------------------- word list (task grid)
  const wordsUrl = state.settings.wordsUrl;
  useEffect(() => {
    if (!wordsUrl) {
      dispatch({ type: "words", words: [...CORE_WORDS] });
      setWordsError(null);
      return;
    }
    let live = true;
    fetch(wordsUrl)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((text) => {
        if (!live) return;
        const words = parseWordList(text);
        dispatch({ type: "words", words });
        setWordsError(words.length ? null : "the word list is empty; using the built-in vocabulary");
      })
      .catch((err: unknown) => {
        if (live) setWordsError(`cannot load the word list (${String(err instanceof Error ? err.message : err)}); using the built-in vocabulary`);
      });
    return () => {
      live = false;
    };
  }, [wordsUrl]);

  // ---------------------------------------------------------------- feedback
  const chosen = state.lastChosen;
  useEffect(() => {
    if (!chosen) return;
    setAnnounce(`Selected ${chosen.label || "an empty tile"}`);
    if (stateRef.current.settings.audioTick) audioTick();
  }, [chosen]);
  useEffect(() => {
    if (state.speech) speak(state.speech.text, state.settings.speechRate);
  }, [state.speech]);

  const applySettings = (s: BoardSettings) => {
    dispatch({ type: "settings", settings: s });
    saveSettings(s);
  };

  // ---------------------------------------------------------------- render
  const page = useMemo(() => buildPage(state), [state.page, state.settings, state.words, state.message, state.speechAvailable]);
  const focus = focusTile(state);
  const row = scanRow(state);
  const label = compositionLabel(state.sources);
  const method = state.method;
  const shown = method ?? state.heldMethod;
  const cursorMode = shown === "cursor_click" || shown === "cursor_dwell";
  const grid = state.settings.layout === "grid";
  const modeText = method ? METHOD_LABEL[method] : "Waiting";
  const paused = !state.active && state.stopReason !== null;
  const input = state.lastInput;

  return (
    <div
      className={`board${grid ? " board-taskgrid" : ""}`}
      data-method={method ?? "none"}
      style={{ ["--text-scale" as string]: String(state.settings.textScale) }}
    >
      <header className="board-head">
        <span className="board-name">Communication board</span>
        <span className="board-tag">Research use only</span>
        <span className="board-status">
          <span className={`dot ${state.active ? "dot-on" : "dot-off"}`} aria-hidden />
          <span data-testid="board-mode" data-mode={method ?? "inactive"}>
            {modeText}
          </span>
        </span>
        <span className="board-spacer" />
        <span className={`board-conn conn-${conn}`} data-testid="board-conn" data-conn={conn}>
          {CONN_TEXT[conn] ?? conn}
        </span>
        <button type="button" className="board-settings-toggle" onClick={() => setShowSettings((v) => !v)} data-testid="board-settings-toggle">
          Settings
        </button>
      </header>

      <div
        className={`board-control ${state.active ? "control-on" : paused ? "control-paused" : "control-none"}`}
        data-testid="board-control"
        data-active={state.active ? "true" : "false"}
        aria-live="assertive"
      >
        {state.active
          ? "Input active"
          : state.waiting.length
            ? `Waiting for the operator to authorize this board (${state.waiting.map((c) => c.replace(/_/g, " ")).join(", ")})`
            : paused
              ? `Paused — ${state.stopReason ?? "input not available"}`
              : "No input"}
        {input && (
          <span className="board-input" data-testid="board-input">
            Input: {inputLabel(input)}
            {dataQualifiers(input).map((q) => ` · ${q}`)}
          </span>
        )}
      </div>

      <div className="board-message-row">
        <div className="board-message" data-testid="board-message">
          {state.message || <span className="placeholder">Message appears here…</span>}
          {state.usable.includes("text_intent") && <span className="caret" aria-hidden />}
        </div>
        {label && (
          <div className="board-text-label" data-testid="board-text-label">
            {label}
          </div>
        )}
      </div>

      <div className="board-hint" data-testid="board-hint">
        {methodHint(method, state.granted, state.settings.dwellMs)}
        {state.settings.confirm === "repeat" && " Choose each tile twice to confirm."}
      </div>

      <div className="board-main">
        <div className="board-area">
          <div
            className="board-grid"
            style={{ gridTemplateColumns: `repeat(${page.cols}, 1fr)`, gridTemplateRows: `repeat(${page.rows}, 1fr)` }}
            role="grid"
            aria-label={grid ? "task grid" : page.kind === "letters" ? "letters" : "phrases"}
            data-testid="board-grid"
            data-cols={page.cols}
            data-rows={page.rows}
          >
            {page.tiles.map((tile, i) => {
              const inRow = row !== null && Math.floor(i / page.cols) === row;
              const isFocus = row !== null ? inRow : focus === i;
              const isPending = state.pending?.page === state.page && state.pending.tile === i;
              const dwelling = state.active && state.dwell.armed && state.dwell.sinceMs !== null && state.dwell.tile === i;
              const flash = chosen && chosen.page === state.page && chosen.tile === i;
              return (
                <div
                  key={`${page.kind}-${i}`}
                  role="gridcell"
                  data-testid={`tile-${i}`}
                  data-active={isFocus ? "true" : "false"}
                  data-pending={isPending ? "true" : undefined}
                  aria-selected={isFocus}
                  className={[
                    "tile",
                    `tile-${tile.kind}`,
                    isFocus ? "tile-active" : "",
                    isPending ? "tile-pending" : "",
                    tile.label ? "" : "tile-empty",
                  ].join(" ")}
                >
                  {flash && <span key={chosen.n} className="tile-flash" aria-hidden />}
                  {dwelling && (
                    <span
                      key={state.dwell.sinceMs}
                      className="dwell-bar"
                      style={{ animationDuration: `${state.settings.dwellMs}ms` }}
                      aria-hidden
                    />
                  )}
                  <span className="tile-label">{tile.label}</span>
                  {tile.kind === "speak" && (
                    <small>{speakLabel(state) === "Speak" ? SPEECH_LABEL : "save to history (speech off or unavailable)"}</small>
                  )}
                  {isPending && <small>select again to confirm</small>}
                </div>
              );
            })}
            {cursorMode && (
              <div
                className={`cursor${state.active ? "" : " cursor-frozen"}`}
                data-testid="board-cursor"
                style={{ left: `${state.cursor.x * 100}%`, top: `${state.cursor.y * 100}%` }}
              />
            )}
          </div>
        </div>

        <aside className="board-history" data-testid="board-history" aria-label="communication history">
          <h2>History</h2>
          {state.history.length === 0 ? (
            <p className="placeholder">Spoken or saved messages appear here.</p>
          ) : (
            <ol>
              {[...state.history].reverse().map((h) => (
                <li key={h.n} data-testid={`history-${h.n}`}>
                  <span className="history-text">{h.text}</span>
                  {h.label && <span className="history-label">{h.label}</span>}
                  {h.input && <span className="history-input">{h.input}</span>}
                </li>
              ))}
            </ol>
          )}
        </aside>
      </div>

      <div className="sr-only" aria-live="polite" data-testid="board-announce">
        {announce}
      </div>

      <footer className="board-foot">
        <span data-testid="board-runtime">{control ? `Runtime: ${control.reason}` : "Runtime: no control state yet"}</span>
        <span data-testid="board-stats">
          {plural(state.selectionCount, "selection")} · {plural(stats.received, "event")} · {plural(stats.deliveryGaps, "delivery gap")}
        </span>
      </footer>

      {showSettings && (
        <SettingsPanel
          settings={state.settings}
          granted={state.granted}
          method={method}
          speechAvailable={state.speechAvailable}
          wordsError={wordsError}
          onChange={applySettings}
          onClearHistory={() => dispatch({ type: "clearHistory" })}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
  );
}
