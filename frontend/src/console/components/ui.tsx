import type { ReactNode } from "react";

export function Panel({
  title,
  right,
  children,
  className = "",
  testId,
}: {
  title: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <section className={`panel ${className}`} data-testid={testId}>
      <header className="panel-head">
        <h2>{title}</h2>
        {right && <div className="panel-right">{right}</div>}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function Kpi({ label, value, unit, tone }: { label: string; value: ReactNode; unit?: string; tone?: "ok" | "warn" | "err" }) {
  return (
    <div className={`kpi ${tone ? `tone-${tone}` : ""}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">
        {value}
        {unit && <span className="kpi-unit">{unit}</span>}
      </div>
    </div>
  );
}

export const fmt = {
  num(v: number | null | undefined, digits = 0): string {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  },
  us(v: number | null | undefined): string {
    if (v === null || v === undefined) return "—";
    return v >= 1000 ? `${(v / 1000).toFixed(2)} ms` : `${v.toFixed(0)} µs`;
  },
  time(ns: number | null | undefined): string {
    if (!ns) return "—";
    return new Date(ns / 1e6).toLocaleTimeString(undefined, { hour12: false });
  },
  ago(ns: number | null | undefined): string {
    if (!ns) return "—";
    const s = Math.max(0, (Date.now() - ns / 1e6) / 1000);
    if (s < 60) return `${s.toFixed(0)}s ago`;
    if (s < 3600) return `${(s / 60).toFixed(0)}m ago`;
    return `${(s / 3600).toFixed(1)}h ago`;
  },
  bytes(n: number): string {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  },
};
