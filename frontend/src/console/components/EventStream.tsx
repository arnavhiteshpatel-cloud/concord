import { useMemo, useState } from "react";
import { EVENT_CAPABILITY, type EventEnvelope, type EventType } from "../../sdk";

const TYPES = Object.keys(EVENT_CAPABILITY) as EventType[];
const VISIBLE_ROWS = 60;

/** Payload summary; decoded events also name the model that produced them. */
export function summary(e: EventEnvelope): string {
  const s = payloadSummary(e);
  return e.provenance.kind === "decoded_intent" && e.provenance.model_id ? `${s}  ⟵ ${e.provenance.model_id}` : s;
}

function payloadSummary(e: EventEnvelope): string {
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
    <div className="events-panel" data-testid="event-stream">
      <div className="btn-row">
        <button
          type="button"
          className="btn btn-small"
          aria-pressed={!!frozen}
          onClick={() => setFrozen(frozen ? null : [...events])}
          data-testid="freeze"
        >
          {frozen ? "Resume view" : "Freeze view"}
        </button>
        <span className="hint">Latest {VISIBLE_ROWS} events. Select a row to inspect its envelope.</span>
      </div>
      <div className="type-filters" role="group" aria-label="Show event types">
        {TYPES.map((t) => (
          <label key={t} className="check filter">
            <input type="checkbox" checked={!hidden.has(t)} onChange={() => toggle(t)} />
            {t}
          </label>
        ))}
      </div>
      <div className="event-table" role="table">
        <div className="event-row event-head" role="row">
          <span>Seq</span>
          <span>Type</span>
          <span>Device</span>
          <span>Provenance</span>
          <span>Quality</span>
          <span>Payload</span>
        </div>
        {rows.map((e) => (
          <div
            key={`${e.session_id}:${e.seq}`}
            className={`event-row ${selected === e ? "sel" : ""}`}
            role="row"
            tabIndex={0}
            onClick={() => setSelected(e)}
            onKeyDown={(k) => (k.key === "Enter" || k.key === " ") && setSelected(e)}
            data-event-type={e.event_type}
          >
            <span className="num">{e.seq}</span>
            <span className="etype">{e.event_type}</span>
            <span className="hint">{e.device_id}</span>
            <span
              className={`prov prov-${e.provenance.kind}`}
              title={e.provenance.model_id ? `model ${e.provenance.model_id}` : e.provenance.adapter}
            >
              {e.provenance.kind}
              {e.provenance.replayed ? " ↺" : ""}
            </span>
            <span className={`num q ${e.quality.score < 0.7 ? "q-low" : ""}`}>{e.quality.score.toFixed(2)}</span>
            <span className="payload">{summary(e)}</span>
          </div>
        ))}
        {rows.length === 0 && <p className="value-muted">No events yet. Connect a source.</p>}
      </div>
      {selected && (
        <div className="inspector">
          <div className="inspector-head">
            <span>Envelope, seq {selected.seq}</span>
            <button type="button" className="btn btn-small" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          <pre data-testid="inspector-json">{compactJson(selected)}</pre>
        </div>
      )}
    </div>
  );
}
