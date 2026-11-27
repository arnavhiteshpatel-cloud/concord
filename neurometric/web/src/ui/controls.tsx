// Small accessible building blocks: native buttons with aria-pressed for choices, steppers made
// of native buttons (operable with one switch), labelled outputs.

import { useId } from "react";

export function Choice<T extends string | number>(props: { legend: string; value: T; options: [T, string][]; onChange: (v: T) => void; hint?: string; row?: number }) {
  const id = useId();
  return (
    <fieldset data-scan-row={props.row}>
      <legend>{props.legend}</legend>
      {props.hint && (
        <p className="muted" id={`${id}-hint`} style={{ marginTop: 0 }}>
          {props.hint}
        </p>
      )}
      <div className="row" role="group" aria-label={props.legend} aria-describedby={props.hint ? `${id}-hint` : undefined}>
        {props.options.map(([v, label]) => (
          <button key={String(v)} type="button" aria-pressed={props.value === v} onClick={() => props.onChange(v)}>
            {label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export function Toggle(props: { label: string; value: boolean; onChange: (v: boolean) => void; hint?: string; id?: string }) {
  const hid = useId();
  return (
    <div className="stack" style={{ marginBottom: 12 }}>
      <button id={props.id} type="button" aria-pressed={props.value} aria-describedby={props.hint ? hid : undefined} onClick={() => props.onChange(!props.value)}>
        {props.label}: {props.value ? "on" : "off"}
      </button>
      {props.hint && (
        <p className="muted" id={hid} style={{ margin: "4px 0 0" }}>
          {props.hint}
        </p>
      )}
    </div>
  );
}

export function Stepper(props: { label: string; value: number; min: number; max: number; step: number; unit?: string; format?: (v: number) => string; onChange: (v: number) => void }) {
  const id = useId();
  const { value, min, max, step } = props;
  const show = props.format ? props.format(value) : `${value}${props.unit ? " " + props.unit : ""}`;
  const clamp = (v: number) => Math.min(max, Math.max(min, Number((Math.round(v / step) * step).toFixed(6))));
  return (
    <div className="stack" style={{ marginBottom: 12 }}>
      <span id={id} style={{ fontWeight: 600, display: "block" }}>
        {props.label}
      </span>
      <div className="stepper" role="group" aria-labelledby={id}>
        <button type="button" aria-label={`Decrease ${props.label}`} disabled={value <= min} onClick={() => props.onChange(clamp(value - step))}>
          −
        </button>
        <output aria-live="polite" aria-labelledby={id}>
          {show}
        </output>
        <button type="button" aria-label={`Increase ${props.label}`} disabled={value >= max} onClick={() => props.onChange(clamp(value + step))}>
          +
        </button>
      </div>
    </div>
  );
}
