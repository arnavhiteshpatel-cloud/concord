import { useMemo, useState } from "react";
import { EVENT_CAPABILITY, type EventEnvelope, type EventType } from "../../sdk";
import { Panel } from "./ui";

const TYPES = Object.keys(EVENT_CAPABILITY) as EventType[];
const VISIBLE_ROWS = 60;

function summary(e: EventEnvelope): string {
  switch (e.event_type) {
    case "intent.pointer":
      return `vx ${e.payload.vx.toFixed(3)}  vy ${e.payload.vy.toFixed(3)}`;
    case "intent.selection":
      return `${e.payload.action}  conf ${e.payload.confidence.toFixed(2)}`;
    case "intent.text":
      return `"${e.payload.text}"  ${e.payload.mode}`;
    case "recording.frame":
      return `${e.payload.channel_count}×${e.payload.samples[0]?.length ?? 0} @ ${e.payload.sample_rate_hz} Hz  #${e.payload.first_sample_index}`;
    case "recording.annotation":
      return `${e.payload.label} = ${String(e.payload.value)}`;
    case "telemetry.sample":
      return e.payload.metrics.map((m) => `${m.name}=${m.value}`).join("  ");
    case "device.status":
      return `${e.payload.state}${e.payload.detail ? ` — ${e.payload.detail}` : ""}`;
    case "features.binned": {
      const c = e.payload.counts;
      const total = c.reduce((a, b) => a + b, 0);
      return `bin ${e.payload.bin_index}  ${e.payload.channel_count} ch  Σ${total} ${e.payload.feature}`;
    }
    case "features.vector":
      return `bin ${e.payload.bin_index}  ${e.payload.channel_count} ch  ${e.payload.feature} ${e.payload.unit}`;
    case "behavior.sample":
    case "intent.kinematics":
      return e.payload.dims.map((d, i) => `${d}=${(e.payload.values[i] ?? 0).toExponential(1)}`).join(" ");
  }
}

function compactJson(e: EventEnvelope): string {
  if (e.event_type === "recording.frame") {
    const p = e.payload;
    const shown = {
      ...e,
      payload: {
        ...p,
        samples: `[${p.channel_count} channels × ${p.samples[0]?.length ?? 0} samples — first: ${p.samples[0]?.slice(0, 4).join(", ")} …]`,
      },
    };
    return JSON.stringify(shown, null, 2);
  }
  return JSON.stringify(e, null, 2);
}

export function EventStream({ events, tick }: { events: EventEnvelope[]; tick: number }) {
  const [hidden, setHidden] = useState<Set<EventType>>(new Set());
  const [frozen, setFrozen] = useState<EventEnvelope[] | null>(null);
  const [selected, setSelected] = useState<EventEnvelope | null>(null);

  const source = frozen ?? events;
  const rows = useMemo(
    () =>
      source
        .filter((e) => !hidden.has(e.event_type))
        .slice(-VISIBLE_ROWS)
        .reverse(),
    // `tick` forces re-derivation: `source` is a mutable ring buffer while live
    [source, hidden, tick],
  );

  const toggle = (t: EventType) =>
    setHidden((h) => {
      const n = new Set(h);
      if (n.has(t)) n.delete(t);
      else n.add(t);
      return n;
    });

  return (
    <Panel
      title="Live event stream"
      className="events-panel"
      testId="event-stream"
      right={
        <button
          className={`btn btn-small ${frozen ? "btn-primary" : ""}`}
          onClick={() => setFrozen(frozen ? null : [...events])}
          data-testid="freeze"
        >
          {frozen ? "Resume view" : "Freeze view"}
        </button>
      }
    >
      <div className="type-filters">
        {TYPES.map((t) => (
          <button
            key={t}
            className={`filter ${hidden.has(t) ? "off" : ""}`}
            onClick={() => toggle(t)}
            title={hidden.has(t) ? "show" : "hide"}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="event-table" role="table">
        <div className="event-row event-head" role="row">
          <span>seq</span>
          <span>type</span>
          <span>device</span>
          <span>provenance</span>
          <span>q</span>
          <span>payload</span>
        </div>
        {rows.map((e) => (
          <div
            key={`${e.session_id}:${e.seq}`}
            className={`event-row ${selected === e ? "sel" : ""}`}
            role="row"
            onClick={() => setSelected(e)}
            data-event-type={e.event_type}
          >
            <span className="mono">{e.seq}</span>
            <span className="mono etype">{e.event_type}</span>
            <span className="mono muted">{e.device_id}</span>
            <span className={`prov prov-${e.provenance.kind}`}>
              {e.provenance.kind}
              {e.provenance.replayed ? " ↺" : ""}
            </span>
            <span className={`mono q ${e.quality.score < 0.7 ? "q-low" : ""}`}>{e.quality.score.toFixed(2)}</span>
            <span className="mono payload">{summary(e)}</span>
          </div>
        ))}
        {rows.length === 0 && <div className="empty">No events yet. Connect a device.</div>}
      </div>
      {selected && (
        <div className="inspector">
          <div className="inspector-head">
            <span>
              Envelope <span className="mono">seq {selected.seq}</span>
            </span>
            <button className="btn btn-small btn-ghost" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          <pre data-testid="inspector-json">{compactJson(selected)}</pre>
        </div>
      )}
    </Panel>
  );
}
