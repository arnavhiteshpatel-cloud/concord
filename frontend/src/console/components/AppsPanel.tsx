import type { ConnectedApp } from "../../sdk";
import { Panel, fmt } from "./ui";

export function AppsPanel({ apps }: { apps: ConnectedApp[] }) {
  return (
    <Panel title="Connected applications" right={<span className="muted">{apps.length}</span>} testId="apps-panel">
      <div className="apps">
        {apps.map((a) => (
          <div key={a.connection_id} className="app" data-testid={`app-${a.app.id}`}>
            <div className="app-top">
              <span className="app-name">{a.app.name}</span>
              <span className={`chip status-${a.negotiation.status}`}>{a.negotiation.status}</span>
            </div>
            <div className="app-meta mono">
              {a.app.kind} · {a.connection_id.slice(0, 12)} · delivered {fmt.num(a.delivered)} · dropped{" "}
              <span className={a.dropped ? "text-err" : ""}>{fmt.num(a.dropped)}</span> · queue {a.queue_depth}
            </div>
            <div className="cap-chips">
              {a.negotiation.granted.map((c) => (
                <span key={c} className="cap cap-granted" title="granted">
                  {c}
                </span>
              ))}
              {a.negotiation.rejected.map((r) => (
                <span
                  key={r.capability}
                  className={`cap cap-rejected ${r.required ? "cap-required" : ""}`}
                  title={`${r.reason}${r.required ? " (required)" : " (optional)"}`}
                >
                  {r.capability}
                </span>
              ))}
            </div>
          </div>
        ))}
        {apps.length === 0 && <div className="empty">No applications connected.</div>}
      </div>
    </Panel>
  );
}
