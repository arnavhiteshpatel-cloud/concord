import { useCallback, useEffect, useState } from "react";
import { consoleApi, type TestReport } from "../api";
import { Panel, fmt } from "./ui";

export function TestsView({ onError }: { onError: (e: unknown) => void }) {
  const [reports, setReports] = useState<TestReport[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(() => {
    consoleApi.tests().then(setReports).catch(onError);
  }, [onError]);
  useEffect(load, [load]);

  if (!reports) return <div className="empty">Loading test reports…</div>;
  return (
    <div className="tests" data-testid="tests-view">
      <div className="tests-intro">
        <p className="muted small">
          Results of the most recent real test runs, read from <code>reports/</code>. This page does not run tests;
          refresh them with <code>make test</code> (unit/integration) and <code>make e2e</code> (browser demo).
        </p>
        <button className="btn btn-small" onClick={load}>
          Reload
        </button>
      </div>
      {reports.map((r) => (
        <Panel
          key={r.name}
          title={r.name}
          right={
            r.available ? (
              <span className={`chip ${r.failed ? "status-suspended" : "status-active"}`}>
                {r.failed ? `${r.failed} failed` : "all passed"}
              </span>
            ) : (
              <span className="chip status-no_device">no report</span>
            )
          }
        >
          {r.available ? (
            <>
              <div className="kpis kpis-small">
                <div className="kpi">
                  <div className="kpi-label">passed</div>
                  <div className="kpi-value text-ok">{r.passed}</div>
                </div>
                <div className="kpi">
                  <div className="kpi-label">failed</div>
                  <div className={`kpi-value ${r.failed ? "text-err" : ""}`}>{r.failed}</div>
                </div>
                <div className="kpi">
                  <div className="kpi-label">skipped</div>
                  <div className="kpi-value">{r.skipped}</div>
                </div>
                <div className="kpi">
                  <div className="kpi-label">duration</div>
                  <div className="kpi-value">
                    {r.duration_s.toFixed(1)}
                    <span className="kpi-unit">s</span>
                  </div>
                </div>
                <div className="kpi">
                  <div className="kpi-label">generated</div>
                  <div className="kpi-value small-val">{fmt.ago(r.generated_at_ns)}</div>
                </div>
              </div>
              <button className="btn btn-small btn-ghost" onClick={() => setOpen(open === r.name ? null : r.name)}>
                {open === r.name ? "Hide" : "Show"} {r.total} test cases
              </button>
              {open === r.name && (
                <table className="table cases">
                  <tbody>
                    {r.cases.map((c, i) => (
                      <tr key={`${c.suite}-${c.name}-${i}`}>
                        <td className={`nowrap text-${c.status === "passed" ? "ok" : c.status === "failed" ? "err" : "muted"}`}>
                          {c.status}
                        </td>
                        <td className="mono muted">{c.suite}</td>
                        <td className="mono">
                          {c.name}
                          {c.message && <div className="case-msg">{c.message}</div>}
                        </td>
                        <td className="r mono nowrap">{(c.time_s * 1000).toFixed(0)} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          ) : (
            <p className="muted">
              {r.error ?? `No ${r.source} found. Run the corresponding make target to generate it.`}
            </p>
          )}
        </Panel>
      ))}
    </div>
  );
}
