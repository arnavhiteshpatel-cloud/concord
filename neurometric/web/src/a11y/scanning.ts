// App-wide switch scanning: one Scanner drives the app's own controls (setup, task list, dialogs,
// results) and, while a task runs, the task's items plus its Pause / Assistance / Stop controls.
// Key listeners are attached to the app root element only (never window/document).

import { useEffect } from "react";
import { Scanner, switchIndexOf, type ScanAction, type ScanTarget, type SwitchConfig } from "../input/switch";

export interface ScanBridge {
  /** A running task supplies its own targets (items + controls). */
  provider: (() => ScanTarget[]) | null;
  /** A running task records scan actions as canonical events. */
  onAction: ((a: ScanAction) => void) | null;
  scanner: Scanner | null;
  /** Session clock used to stamp switch presses (task recorder clock while a task runs). */
  fromTimeStamp: ((ts: number) => number) | null;
}

export const scanBridge: ScanBridge = { provider: null, onAction: null, scanner: null, fromTimeStamp: null };

const SELECTOR = 'button, a[href], input:not([type="hidden"]), select, textarea, summary, [data-scan-target]';

function isVisible(el: HTMLElement): boolean {
  if (el.closest("[hidden], [inert]")) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}

function nativeSet(el: HTMLInputElement | HTMLSelectElement, value: string): void {
  const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  setter?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

/** Operate a native control with a single "activate" action. */
export function activateElement(el: HTMLElement): void {
  if (el instanceof HTMLInputElement && el.type === "range") {
    // One-switch operation of a slider: each activation steps up, wrapping to the minimum.
    const min = Number(el.min || 0);
    const max = Number(el.max || 100);
    const step = Number(el.step || 1) || 1;
    let v = Number(el.value) + step;
    if (v > max + 1e-9) v = min;
    nativeSet(el, String(v));
    return;
  }
  if (el instanceof HTMLSelectElement) {
    const i = (el.selectedIndex + 1) % el.options.length;
    nativeSet(el, el.options[i].value);
    return;
  }
  if (el instanceof HTMLInputElement && ["text", "number", "search", "email", "tel", "url", "password"].includes(el.type)) {
    el.focus();
    return;
  }
  if (el instanceof HTMLTextAreaElement) {
    el.focus();
    return;
  }
  el.click();
}

export function domTargets(root: HTMLElement): ScanTarget[] {
  const dialog = root.querySelector<HTMLElement>("dialog[open]");
  const scope = dialog ?? root.querySelector<HTMLElement>("[data-scan-root]") ?? root;
  const els = [...scope.querySelectorAll<HTMLElement>(SELECTOR)].filter(
    (el) => !(el as HTMLButtonElement).disabled && !el.hasAttribute("data-scan-skip") && isVisible(el),
  );
  return els.map((el, i) => {
    const row = el.closest<HTMLElement>("[data-scan-row]")?.dataset.scanRow;
    return {
      id: el.id || `ui-${i}`,
      el,
      row: row !== undefined ? Number(row) : undefined,
      label: el.getAttribute("aria-label") ?? el.textContent ?? "",
      role: "control" as const,
      activate: () => activateElement(el),
    };
  });
}

let highlighted: HTMLElement[] = [];

export function renderHighlight(targets: ScanTarget[], level: "item" | "row" | "none"): void {
  for (const el of highlighted) el.classList.remove("scan-hl", "scan-hl-row");
  highlighted = [];
  if (level === "none") return;
  for (const t of targets) {
    if (!t.el) continue;
    t.el.classList.add(level === "row" ? "scan-hl-row" : "scan-hl");
    highlighted.push(t.el);
  }
  const first = targets[0]?.el;
  if (first) {
    first.focus({ preventScroll: true });
    first.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }
}

/** Enable switch scanning over the app root. */
export function useAppScanning(root: HTMLElement | null, cfg: SwitchConfig, enabled: boolean): void {
  useEffect(() => {
    if (!root || !enabled) return;
    const now = () => performance.now();
    const scanner = new Scanner(
      cfg,
      () => (scanBridge.provider ? scanBridge.provider() : domTargets(root)),
      renderHighlight,
      (a) => scanBridge.onAction?.(a),
      () => (scanBridge.fromTimeStamp ? scanBridge.fromTimeStamp(now()) : now()),
    );
    scanBridge.scanner = scanner;
    const down = (ev: KeyboardEvent) => {
      const idx = switchIndexOf(cfg, ev);
      if (idx < 0) return;
      ev.preventDefault();
      ev.stopPropagation();
      if (ev.repeat) return;
      const t = scanBridge.fromTimeStamp ? scanBridge.fromTimeStamp(ev.timeStamp) : ev.timeStamp;
      scanner.press(idx, t);
    };
    const up = (ev: KeyboardEvent) => {
      if (switchIndexOf(cfg, ev) >= 0) {
        ev.preventDefault();
        ev.stopPropagation();
      }
    };
    root.addEventListener("keydown", down, true);
    root.addEventListener("keyup", up, true);
    // Restart scanning when the set of controls changes (screen change, dialog opened).
    let last: HTMLElement[] = [];
    const mo = new MutationObserver(() => {
      if (scanBridge.provider) return; // the task manages its own resets
      const now = domTargets(root).map((t) => t.el!) as HTMLElement[];
      const same = now.length === last.length && now.every((e, i) => e === last[i]);
      last = now;
      if (!same) scanner.reset();
    });
    mo.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ["open", "hidden", "disabled"] });
    last = domTargets(root).map((t) => t.el!) as HTMLElement[];
    return () => {
      root.removeEventListener("keydown", down, true);
      root.removeEventListener("keyup", up, true);
      mo.disconnect();
      scanner.stop();
      scanner.dispose();
      renderHighlight([], "none");
      if (scanBridge.scanner === scanner) scanBridge.scanner = null;
    };
  }, [root, enabled, cfg]);
}
