import type { ConnectedApp } from "../../sdk";
import { fmt } from "./ui";

export function AppsPanel({ apps }: { apps: ConnectedApp[] }) {
  return (
    <div className="apps" data-testid="apps-panel">
        {apps.map((a) => (
          <div key={a.connection_id} className="app" data-testid={`app-${a.app.id}`}>
            <div className="app-top">
              <span className="app-name">{a.app.name}</span>
              <span className="hint">{a.negotiation.status.replace(/_/g, " ")}</span>
            </div>
            <div className="app-meta num">
              {a.app.kind} · {a.connection_id.slice(0, 12)} · delivered {fmt.num(a.delivered)} · dropped{" "}
              {fmt.num(a.dropped)} · queue {a.queue_depth}
            </div>
            <div className="app-meta">
              Granted: {a.negotiation.granted.length ? a.negotiation.granted.join(", ") : "none"}
              {a.negotiation.rejected.length > 0 && (
                <>
                  {" "}
                  · Not granted:{" "}
                  {a.negotiation.rejected
                    .map((r) => `${r.capability}${r.required ? " (required)" : ""}`)
                    .join(", ")}
                </>
              )}
            </div>
          </div>
        ))}
      {apps.length === 0 && <p className="value-muted">No applications connected.</p>}
    </div>
  );
}
