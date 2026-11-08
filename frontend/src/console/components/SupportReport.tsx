// Milestone 5 (D), Advanced → Support report: the same report as `concord doctor`, made by the
// running server. It contains no neural data and no personal data (its last section lists
// exactly what is left out).

import { useState } from "react";
import { useLoggedAction } from "../context";
import { researchApi, type DoctorReport } from "../researchApi";

export function SupportReport() {
  const action = useLoggedAction();
  const [report, setReport] = useState<DoctorReport | null>(null);
  const [jsonUrl, setJsonUrl] = useState<string | null>(null);
  const create = async () => {
    const r = await action.run(researchApi.doctor);
    if (r) {
      setReport(r);
      if (jsonUrl) URL.revokeObjectURL(jsonUrl);
      setJsonUrl(URL.createObjectURL(new Blob([JSON.stringify(r, null, 1)], { type: "application/json" })));
    }
  };
  const problems = report?.checks.filter((c) => c.status === "warn" || c.status === "fail") ?? [];
  return (
    <div data-testid="support-report">
      <p className="hint">
        For whoever supports this installation: versions, optional components, ports, data-directory permissions, disk space
        and recent log problems (redacted). Same as <code>concord doctor</code> in a terminal.
      </p>
      <div className="btn-row">
        <button type="button" className="btn" disabled={action.busy} onClick={create} data-testid="support-create">
          Create support report
        </button>
      </div>
      {action.error && <p className="error-text">{action.error}</p>}
      {report && (
        <div className="subform" data-testid="support-result">
          <p data-testid="support-summary">
            {report.summary.fail} failed · {report.summary.warn} warnings · {report.summary.ok} ok
          </p>
          {problems.length > 0 && (
            <ul className="support-problems">
              {problems.map((c) => (
                <li key={c.id}>
                  <strong>{c.title}</strong>: {c.detail}
                  {c.hint ? ` — ${c.hint}` : ""}
                </li>
              ))}
            </ul>
          )}
          <p>
            {jsonUrl && (
              <a href={jsonUrl} download="concord-support.json" data-testid="support-json">
                Download JSON
              </a>
            )}{" "}
            ·{" "}
            <a href={researchApi.doctorMarkdownUrl} download="concord-support.md" data-testid="support-md">
              Download Markdown
            </a>
          </p>
          <details>
            <summary className="hint">Not included in the report</summary>
            <ul className="hint">
              {report.excluded.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </details>
        </div>
      )}
    </div>
  );
}
