import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { Tone } from "../wording";

/** A sub-section inside Advanced or a sheet: a plain heading and its content. */
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
        <h3>{title}</h3>
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
      <div className="kpi-value num">
        {value}
        {unit && <span className="kpi-unit">{unit}</span>}
      </div>
    </div>
  );
}

/** A small status dot. The colour is the only place status colours appear. */
export function Dot({ tone }: { tone: Tone }) {
  return <span className={`dot dot-${tone}`} aria-hidden />;
}

/** One row of the session screen: research term, one plain line, values, actions. */
export function Row({
  title,
  explain,
  actions,
  children,
  testId,
}: {
  title: string;
  explain: string;
  actions?: ReactNode;
  children?: ReactNode;
  testId: string;
}) {
  const id = useId();
  return (
    <section className="row" aria-labelledby={id} data-testid={testId}>
      <div className="row-head">
        <div>
          <h2 id={id}>{title}</h2>
          <p className="explain">{explain}</p>
        </div>
        {actions && <div className="row-actions">{actions}</div>}
      </div>
      {children && <div className="row-body">{children}</div>}
    </section>
  );
}

/** A collapsed-by-default disclosure. `keepMounted` keeps hidden content alive (e.g. an embedded app). */
export function Disclosure({
  title,
  children,
  defaultOpen = false,
  keepMounted = false,
  testId,
  className = "",
}: {
  title: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  keepMounted?: boolean;
  testId?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <div className={`disclosure ${className}`} data-testid={testId} data-open={open}>
      <button
        type="button"
        className="disclosure-toggle"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        data-testid={testId ? `${testId}-toggle` : undefined}
      >
        <span className="chev" aria-hidden />
        {title}
      </button>
      <div id={id} className="disclosure-body" hidden={!open}>
        {(open || keepMounted) && children}
      </div>
    </div>
  );
}

/** A side sheet over the session screen (dialog). Escape or "Close" dismisses it. */
export function Sheet({
  title,
  onClose,
  children,
  testId,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  testId?: string;
}) {
  const id = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    heading.current?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRef.current();
    };
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("keydown", key);
      before?.focus?.();
    };
  }, []);
  return (
    <div className="sheet-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby={id} data-testid={testId}>
        <header className="sheet-head">
          <h2 id={id} ref={heading} tabIndex={-1}>
            {title}
          </h2>
          <button type="button" className="btn" onClick={onClose} data-testid="sheet-close">
            Close
          </button>
        </header>
        <div className="sheet-body">{children}</div>
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
    if (s < 60) return `${s.toFixed(0)} s ago`;
    if (s < 3600) return `${(s / 60).toFixed(0)} min ago`;
    return `${(s / 3600).toFixed(1)} h ago`;
  },
  bytes(n: number): string {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  },
};
