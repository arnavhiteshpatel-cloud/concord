import { useCallback, useEffect, useState } from "react";
import { consoleApi, type TestReport } from "../api";
import { errorText } from "../hooks";
import { Panel, fmt } from "./ui";

export function TestsView() {
  const [reports, setReports] = useState<TestReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(() => {
    consoleApi
      .tests()
      .then((r) => {
        setReports(r);
        setError(null);
      })
      .catch((e: unknown) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);

  if (error) return <p className="error-text">{error}</p>;
  if (!reports) return <p className="value-muted">Loading test reports…</p>;
  if (!reports.some((r) => r.available))
    return (
      <p className="hint" data-testid="tests-none">
        No test results on this computer. This section shows the results of Concord&apos;s own test suite when it runs
        from its source code (<code>make test</code>, <code>make e2e</code>); an installed Concord has none, and it
        does not affect how Concord works. The results of each release are on the project&apos;s GitHub page.
      </p>
    );
  return (
    <div className="tests" data-testid="tests-view">
      <div className="btn-row">
        <p className="hint">
          Results of the most recent real test runs, read from <code>reports/</code>. This page does not run tests;
          refresh them with <code>make test</code> and <code>make e2e</code>.
        </p>
        <button type="button" className="btn btn-small" onClick={load}>
          Reload
        </button>
      </div>
      {reports.map((r) => (
        <Panel key={r.name} title={r.name}>
          {r.available ? (
            <>
              <p className="num">
                {r.failed ? <span className="error-text">{r.failed} failed</span> : "All passed"} · {r.passed} passed ·{" "}
                {r.skipped} skipped · {r.duration_s.toFixed(1)} s · generated {fmt.ago(r.generated_at_ns)}
              </p>
              <button type="button" className="btn btn-small btn-quiet" onClick={() => setOpen(open === r.name ? null : r.name)}>
                {open === r.name ? "Hide" : "Show"} {r.total} test cases
              </button>
              {open === r.name && (
                <table className="table cases">
                  <tbody>
                    {r.cases.map((c, i) => (
                      <tr key={`${c.suite}-${c.name}-${i}`}>
                        <td className={`nowrap ${c.status === "failed" ? "error-text" : "hint"}`}>{c.status}</td>
                        <td className="hint">{c.suite}</td>
                        <td>
                          {c.name}
                          {c.message && <div className="case-msg">{c.message}</div>}
                        </td>
                        <td className="r num nowrap">{(c.time_s * 1000).toFixed(0)} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          ) : (
            <p className="value-muted">
              {r.error ?? `No ${r.source} found. Run the corresponding make target to generate it.`}
            </p>
          )}
        </Panel>
      ))}
    </div>
  );
}
