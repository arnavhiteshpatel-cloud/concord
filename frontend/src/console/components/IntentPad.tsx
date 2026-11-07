// Simulated intention source: the operator stands in for the participant's
// intent. Inputs go to /api/v1/sim/* and enter the simulated device, which then
// emits device-native packets that the runtime normalizes. Nothing here talks
// to the board directly.

import { useCallback, useEffect, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import type { RuntimeSnapshot } from "../../sdk";
import { consoleApi } from "../api";
import { Panel } from "./ui";

const SEND_INTERVAL_MS = 50;
const KEEPALIVE_MS = 200; // server dead-man is 500 ms
const KEY_SPEED = 0.6;

export function IntentPad({
  runtime,
  onError,
}: {
  runtime: RuntimeSnapshot | null;
  onError: (e: unknown) => void;
}) {
  const device = runtime?.device;
  const live = device?.kind === "simulated" && runtime?.state === "streaming";
  const supports = (cap: string) => !!device?.capabilities.some((c) => c.capability === cap);
  const canPointer = live && supports("pointer_intent");
  const canSelect = live && supports("selection");
  const canText = live && supports("text_intent");

  const padRef = useRef<HTMLDivElement>(null);
  const vec = useRef({ vx: 0, vy: 0 });
  const lastSent = useRef({ vx: 0, vy: 0, at: 0 });
  const dragging = useRef(false);
  const keys = useRef(new Set<string>());
  const [knob, setKnob] = useState({ x: 0, y: 0 });
  const [text, setText] = useState("");
  const [sent, setSent] = useState(0);

  const push = useCallback(
    (force = false) => {
      if (!canPointer) return;
      const { vx, vy } = vec.current;
      const now = performance.now();
      const changed = vx !== lastSent.current.vx || vy !== lastSent.current.vy;
      const moving = vx !== 0 || vy !== 0;
      if (!force && !changed && !(moving && now - lastSent.current.at > KEEPALIVE_MS)) return;
      if (!force && changed && now - lastSent.current.at < SEND_INTERVAL_MS) return;
      lastSent.current = { vx, vy, at: now };
      consoleApi.simPointer(vx, vy).catch(onError);
    },
    [canPointer, onError],
  );

  useEffect(() => {
    const t = setInterval(() => push(), SEND_INTERVAL_MS);
    return () => clearInterval(t);
  }, [push]);

  const select = useCallback(() => {
    if (!canSelect) return;
    consoleApi
      .simSelect()
      .then(() => setSent((n) => n + 1))
      .catch(onError);
  }, [canSelect, onError]);

  const setVec = (vx: number, vy: number) => {
    vec.current = { vx, vy };
    setKnob({ x: vx, y: vy });
  };

  const fromPointer = (e: RPointerEvent<HTMLDivElement>) => {
    const el = padRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    let vx = ((e.clientX - r.left) / r.width) * 2 - 1;
    let vy = ((e.clientY - r.top) / r.height) * 2 - 1;
    const mag = Math.hypot(vx, vy);
    if (mag > 1) {
      vx /= mag;
      vy /= mag;
    }
    if (mag < 0.08) vx = vy = 0; // dead zone
    setVec(Math.round(vx * 100) / 100, Math.round(vy * 100) / 100);
  };

  useEffect(() => {
    const isTyping = (t: EventTarget | null) =>
      t instanceof HTMLElement && (t.tagName === "INPUT" || t.tagName === "TEXTAREA");
    const fromKeys = () => {
      const k = keys.current;
      const vx = (k.has("ArrowRight") || k.has("d") ? 1 : 0) - (k.has("ArrowLeft") || k.has("a") ? 1 : 0);
      const vy = (k.has("ArrowDown") || k.has("s") ? 1 : 0) - (k.has("ArrowUp") || k.has("w") ? 1 : 0);
      if (!dragging.current) setVec(vx * KEY_SPEED, vy * KEY_SPEED);
    };
    const down = (e: KeyboardEvent) => {
      if (isTyping(e.target)) return;
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        if (!e.repeat) select();
        return;
      }
      if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "w", "a", "s", "d"].includes(e.key)) {
        e.preventDefault();
        keys.current.add(e.key);
        fromKeys();
      }
    };
    const up = (e: KeyboardEvent) => {
      if (keys.current.delete(e.key)) fromKeys();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [select]);

  const sendText = () => {
    const t = text.trim();
    if (!t || !canText) return;
    consoleApi
      .simText(t.slice(0, 32))
      .then(() => {
        setText("");
        setSent((n) => n + 1);
      })
      .catch(onError);
  };

  return (
    <Panel
      title="Simulated intention source"
      right={<span className="chip plain prov-simulated_intent">operator → simulator</span>}
      className="intent-panel"
      testId="intent-pad"
    >
      <p className="muted small">
        Stands in for the participant's intent. Feeds the <b>simulated device</b>, which emits its own
        native packets; the board only sees standardized runtime events. No neural decoding involved.
      </p>
      <div className="pad-row">
        <div
          ref={padRef}
          className={`pad ${canPointer ? "" : "pad-disabled"}`}
          data-testid="pointer-pad"
          onPointerDown={(e) => {
            if (!canPointer) return;
            dragging.current = true;
            e.currentTarget.setPointerCapture(e.pointerId);
            fromPointer(e);
          }}
          onPointerMove={(e) => dragging.current && fromPointer(e)}
          onPointerUp={() => {
            dragging.current = false;
            setVec(0, 0);
            push(true);
          }}
          onPointerCancel={() => {
            dragging.current = false;
            setVec(0, 0);
            push(true);
          }}
        >
          <div className="pad-cross" />
          {canPointer && (
            <div className="pad-knob" style={{ left: `${50 + knob.x * 45}%`, top: `${50 + knob.y * 45}%` }} />
          )}
          {!canPointer && (
            <div className="pad-overlay">
              {live ? `${device?.display_name} has no pointer_intent` : "connect a simulated device"}
            </div>
          )}
        </div>
        <div className="pad-side">
          <button className="btn btn-primary btn-big" disabled={!canSelect} onClick={select} data-testid="sim-select">
            Select
          </button>
          <div className="kbd-hint">
            <kbd>Space</kbd> select · <kbd>←↑↓→</kbd>/<kbd>WASD</kbd> move
          </div>
          <div className="vec mono">
            v = ({knob.x.toFixed(2)}, {knob.y.toFixed(2)})
          </div>
          <div className="muted small">discrete intents sent: {sent}</div>
        </div>
      </div>
      <form
        className="text-row"
        onSubmit={(e) => {
          e.preventDefault();
          sendText();
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={32}
          placeholder={canText ? "text intent, e.g. hi" : "text_intent not supported by this device"}
          disabled={!canText}
          data-testid="sim-text"
        />
        <button className="btn" disabled={!canText || !text.trim()} type="submit" data-testid="sim-text-send">
          Send text
        </button>
      </form>
    </Panel>
  );
}
