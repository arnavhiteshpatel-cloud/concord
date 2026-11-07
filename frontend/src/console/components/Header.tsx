import type { ConnectionStatus, DeviceDescriptor, RuntimeSnapshot } from "../../sdk";
import { isLiveSource, type DiagnosticsSnapshot } from "../api";
import { fmt } from "./ui";

/** What kind of data the connected source produces — derived only from the descriptor. */
export function dataBadge(device: DeviceDescriptor | null | undefined): { text: string; className: string; title: string } | null {
  if (!device) return null;
  if (device.synthetic)
    return { text: "SIMULATED DATA", className: "badge-sim", title: "The connected source generates synthetic data" };
  if (device.kind === "stream")
    return {
      text: "LIVE STREAM · ORIGIN UNVERIFIED",
      className: "badge-stream",
      title: "External live stream: BrainOS cannot verify whether it comes from hardware, a file player or a simulator",
    };
  if (device.kind === "replay" && isLiveSource(device))
    // An external stream whose publisher declares prerecorded content: the declaration is not
    // verifiable, and the publisher's stream name never makes it "human".
    return {
      text: "RECORDED DATA · STREAMED REPLAY (DECLARED)",
      className: "badge-real",
      title: "The publisher declares that this live stream replays prerecorded data — not a live implant",
    };
  if (device.kind === "replay") {
    const human = /human/i.test(device.display_name);
    return {
      text: human ? "RECORDED HUMAN DATA · OFFLINE REPLAY" : "RECORDED DATA · OFFLINE REPLAY",
      className: "badge-real",
      title: "Genuine recorded data replayed from a file — not a live implant",
    };
  }
  return { text: "DEVICE DATA", className: "badge-real", title: "Non-synthetic data from a connected device" };
}

export function Header({
  runtime,
  conn,
  diag,
}: {
  runtime: RuntimeSnapshot | null;
  conn: ConnectionStatus;
  diag: DiagnosticsSnapshot | null;
}) {
  const state = runtime?.state ?? "unknown";
  const badge = dataBadge(runtime?.device);
  const rate = diag?.event_types.reduce((a, t) => a + t.rate_hz, 0) ?? 0;
  return (
    <header className="topbar">
      <div className="brand">
        <div className="logo" aria-hidden>
          <span />
          <span />
          <span />
        </div>
        <div>
          <div className="brand-name">BrainOS</div>
          <div className="brand-sub">Runtime Console · v0.1 MVP</div>
        </div>
      </div>
      <div className="topbar-mid">
        <span className={`state-pill state-${state}`} data-testid="runtime-state">
          {state}
        </span>
        <div className="topbar-field">
          <span className="label">device</span>
          <span data-testid="runtime-device">{runtime?.device?.display_name ?? "none"}</span>
        </div>
        <div className="topbar-field">
          <span className="label">session</span>
          <span className="mono">{runtime?.session_id?.slice(0, 12) ?? "—"}</span>
        </div>
        <div className="topbar-field">
          <span className="label">events/s</span>
          <span className="mono">{fmt.num(rate, 0)}</span>
        </div>
        <div className="topbar-field">
          <span className="label">pipeline p95</span>
          <span className="mono">{fmt.us(diag?.pipeline_latency.p95_us)}</span>
        </div>
        {runtime?.recording && (
          <span className="chip rec" data-testid="recording-indicator">
            REC {runtime.recording}
          </span>
        )}
      </div>
      <div className="topbar-right">
        <span className={`chip conn-${conn}`}>stream {conn}</span>
        <span className="chip plain badge-ro" title="v1 has no write or stimulation path">
          READ-ONLY
        </span>
        {badge && (
          <span className={`chip plain ${badge.className}`} title={badge.title} data-testid="data-badge">
            {badge.text}
          </span>
        )}
      </div>
    </header>
  );
}
