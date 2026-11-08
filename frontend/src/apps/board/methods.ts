// Communication board — input methods and when each is available. Pure.
//
// Availability comes ONLY from the negotiated capabilities (never from a device id):
//   cursor_click  pointer_intent + selection     cursor moves; a click (selection) chooses
//   cursor_dwell  pointer_intent                 cursor moves; resting on a tile chooses it
//                                                (dwell selection: a board interaction, never
//                                                a neural click)
//   navigate      navigation                     navigation moves the highlight; selection
//                                                chooses (without selection: dwell on the
//                                                highlighted tile)
//   direct        selection                      select = next tile, activate = choose,
//                                                cancel = undo (sources with several actions)
//   scan          selection                      the board highlights tiles in turn; one
//                                                switch (any select/activate) chooses
// "auto" takes the first available in this order: cursor_click, cursor_dwell, navigate,
// direct (only once the source has sent an activate or cancel action), scan.

import type { Capability } from "../../sdk";

export type Method = "cursor_click" | "cursor_dwell" | "scan" | "navigate" | "direct";
export type MethodChoice = "auto" | Method;

export const METHOD_ORDER: readonly Method[] = ["cursor_click", "cursor_dwell", "navigate", "direct", "scan"];

export const METHOD_LABEL: Record<Method, string> = {
  cursor_click: "Pointer and click",
  cursor_dwell: "Pointer with dwell selection",
  scan: "Scanning",
  navigate: "Directional navigation",
  direct: "Direct selection",
};

/** The capabilities a method needs before it can act (all must be usable). */
export function methodNeeds(m: Method, granted: readonly Capability[]): Capability[] {
  switch (m) {
    case "cursor_click":
      return ["pointer_intent", "selection"];
    case "cursor_dwell":
      return ["pointer_intent"];
    case "navigate":
      return granted.includes("selection") ? ["navigation", "selection"] : ["navigation"];
    case "scan":
    case "direct":
      return ["selection"];
  }
}

export function availableMethods(granted: readonly Capability[]): Method[] {
  const has = (c: Capability) => granted.includes(c);
  const out: Method[] = [];
  if (has("pointer_intent") && has("selection")) out.push("cursor_click");
  if (has("pointer_intent")) out.push("cursor_dwell");
  if (has("navigation")) out.push("navigate");
  if (has("selection")) out.push("direct", "scan");
  return out;
}

/** The method in effect: the override if it is available, else the automatic choice. */
export function chooseMethod(choice: MethodChoice, granted: readonly Capability[], sawDirectActions: boolean): Method | null {
  const avail = availableMethods(granted);
  if (choice !== "auto" && avail.includes(choice)) return choice;
  for (const m of METHOD_ORDER) {
    if (!avail.includes(m)) continue;
    if (m === "direct" && !sawDirectActions) continue;
    return m;
  }
  return null;
}

export function methodHint(m: Method | null, granted: readonly Capability[], dwellMs: number): string {
  const s = (dwellMs / 1000).toFixed(1);
  switch (m) {
    case "cursor_click":
      return "Move the cursor to a tile, then click to choose it.";
    case "cursor_dwell":
      return `Move the cursor to a tile and rest there for ${s} s to choose it (dwell selection).`;
    case "navigate":
      return granted.includes("selection")
        ? "Move the highlight with up / down / left / right (or next / previous), then select."
        : `Move the highlight with up / down / left / right; resting on a tile for ${s} s chooses it (dwell selection).`;
    case "direct":
      return "Select moves to the next tile, activate chooses it, cancel undoes.";
    case "scan":
      return "Tiles are highlighted in turn. Select when the one you want is highlighted.";
    default:
      return "Waiting for a source that can move a cursor, move a highlight, or make a selection.";
  }
}
