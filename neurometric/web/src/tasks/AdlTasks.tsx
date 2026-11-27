// F1-F7 simulated digital activities of daily living. IN-APP ONLY: fictional contacts and pages,
// nothing is sent, no external network. Screen geometry comes from the Python simulator's
// adl_layouts() (exported to public/battery/adl_layouts.json) so simulated and live runs present
// the same screens. Item 0 of every screen is Back (error recovery).

import { useEffect, useRef, useState } from "react";
import { ItemButton, fmt, type TaskApi, type TaskItem } from "./api";
import type { AdlScreen } from "./stimuli";
import type { ProvisionalSummary } from "./session";

interface Flow {
  cue: string;
  title: string[];
  labels: string[][]; // labels for items 1..n of each screen (item 0 = Back)
  targets?: number[]; // overrides layout targets (repetitions)
}

const CONTACTS = ["Avery Quinn", "Blake Morgan", "Casey Rivers", "Devon Hart", "Emery Stone", "Finley Brooks", "Gray Ellis", "Harper Lane", "Indigo Reyes", "Jules Carter"];
const TILES = ["Hello", "Can you", "Please", "Thank you", "Today", "call me", "Yes", "No", "later"];
const MENUS = ["File", "Edit", "View", "Insert", "Help"];
const SUB: Record<string, string[]> = {
  File: ["New", "Open", "Save", "Print", "Share", "Close"],
  Edit: ["Undo", "Redo", "Cut", "Copy", "Paste", "Find"],
  View: ["Zoom in", "Zoom out", "Full screen", "Show ruler", "Dark mode", "Reset view"],
  Insert: ["Picture", "Table", "Link", "Date", "Symbol", "Comment"],
  Help: ["Guide", "Shortcuts", "Contact support", "Report a problem", "About", "Updates"],
};
const WORDS = ["yes", "no", "I", "you", "want", "help", "please", "stop", "more", "drink", "eat", "need", "bed", "now", "later", "music", "toilet", "water", "pain", "thank you"];
const DAYS = Array.from({ length: 35 }, (_, d) => (d < 30 ? `${d + 1}` : `Next ${d - 29}`));
const SLOTS = ["9:00", "9:30", "10:00", "10:30", "11:00", "13:00", "14:00", "15:30"];
const FIELDS: [string, string[]][] = [
  ["Preferred contact", ["Phone", "Email", "Letter", "Text message"]],
  ["Appointment time", ["Morning", "Midday", "Afternoon", "Evening"]],
  ["Transport needed", ["Yes", "No", "Not sure", "Prefer not to say"]],
  ["Reminder", ["None", "1 day before", "2 days before", "1 week before"]],
];
const LINKS1 = ["Home", "News", "Events", "Opening hours", "Classes", "Contact", "Accessibility", "Site map"];
const LINKS2 = ["Pottery", "Chess club", "Choir", "Gardening", "Yoga", "Book club", "Cooking", "Painting"];

// F3 repetitions: [menu item index, submenu item index] in layout item numbering
const F3_REPS = [
  [3, 9],
  [2, 11],
  [4, 7],
  [5, 8],
];
const F6_REPS = [
  [3, 12, 18],
  [7, 6, 14],
];

function flowFor(task: string, rep: number): Flow {
  switch (task) {
    case "F1":
      return { cue: "Open the contact Gray Ellis.", title: ["Contacts (simulated)"], labels: [CONTACTS] };
    case "F2": {
      const tilesSend = [...TILES, "Send"];
      return {
        cue: "Send Casey Rivers the message “Can you call me later”. Nothing is really sent.",
        title: ["Apps", "New message: choose recipient", "Compose", "Compose", "Compose", "Compose"],
        labels: [["Photos", "Messages", "Music", "Weather"], CONTACTS.slice(0, 6), tilesSend, tilesSend, tilesSend, tilesSend],
      };
    }
    case "F3": {
      const [m, s] = F3_REPS[rep % F3_REPS.length];
      const menu = MENUS[m - 1];
      return {
        cue: `Choose ${menu}, then ${SUB[menu][s - 6]}.`,
        title: ["Menu bar", `${menu} menu`],
        labels: [MENUS, [...MENUS, ...SUB[menu]]],
        targets: [m, s],
      };
    }
    case "F4":
      return { cue: "Book an appointment on day 18 at 10:30.", title: ["Choose a date", "Choose a time", "Confirm"], labels: [DAYS, SLOTS, ["Confirm booking"]] };
    case "F5":
      return {
        cue: "Fill in the form: contact by Email, Evening appointment, transport Yes, reminder 2 days before. Then Submit.",
        title: [...FIELDS.map(([f]) => f), "Review"],
        labels: [...FIELDS.map(([, o]) => o), ["Submit"]],
      };
    case "F6": {
      const t = F6_REPS[rep % F6_REPS.length];
      const msg = t.map((k) => WORDS[k - 1]).join(" ");
      return { cue: `Build the message “${msg}” on the board.`, title: ["Board", "Board", "Board"], labels: [WORDS, WORDS, WORDS], targets: t };
    }
    case "F7":
      return { cue: "On the community centre website, open Classes, then find Chess club.", title: ["Community centre (simulated page)", "Classes"], labels: [LINKS1, LINKS2] };
  }
  return { cue: "", title: [], labels: [] };
}

const REPS: Record<string, number> = { F3: 4, F6: 2 };

export function AdlTask({ api, layouts }: { api: TaskApi; layouts: Record<string, AdlScreen[]> }) {
  const task = api.stim.task_id;
  const screens = layouts[task] ?? [];
  const nRep = Math.max(1, Math.min(REPS[task] ?? 1, api.limits.trials ?? 99, api.settings.short ? 1 : 99));
  const [rep, setRep] = useState(0);
  const [step, setStep] = useState(0);
  const [wrong, setWrong] = useState<string | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [done, setDone] = useState(false);
  const errors = useRef(0);
  const rows = useRef<{ time: number; errors: number; completed: boolean }[]>([]);
  const flow = flowFor(task, rep);
  const scr = screens[step];
  const target = flow.targets?.[step] ?? scr?.target ?? -1;

  const items: TaskItem[] = !scr
    ? []
    : wrong !== null
      ? [{ ...scr.items[0], id: "back", label: "Back" }]
      : scr.items
          .map((g, k) => ({ id: k === 0 ? "back" : `item-${k}`, x: g.x, y: g.y, w: g.w, h: g.h, label: k === 0 ? "Back" : flow.labels[step]?.[k - 1] ?? `Item ${k}`, row: k === 0 ? 0 : 1 + Math.floor((g.y - 0) / 120) }))
          .filter((it) => !(it.id === "back" && step === 0 && chosen.length === 0));

  const summarize = (): ProvisionalSummary => {
    const r = rows.current;
    const ok = r.filter((x) => x.completed);
    const values = { trials: r.length, completion_rate: r.length ? ok.length / r.length : NaN, time_to_complete_ms_mean: ok.length ? ok.reduce((a, x) => a + x.time, 0) / ok.length : NaN, wrong_selections: r.reduce((a, x) => a + x.errors, 0) };
    return { values, rows: [["Attempts", String(r.length)], ["Completed", `${ok.length} of ${r.length}`], ["Mean time to complete", fmt(values.time_to_complete_ms_mean / 1000, 1) + " s"], ["Wrong selections", String(values.wrong_selections)]] };
  };

  const endTrial = (outcome: "completed" | "abandoned", t: number) => {
    rows.current.push({ time: t - api.session.lastStimT, errors: errors.current, completed: outcome === "completed" });
    api.session.marker("trial_end", { trial: rep, outcome, wrong_selections: errors.current }, t);
    if (rep + 1 >= nRep) {
      setDone(true);
      api.finish(summarize());
    } else {
      setRep(rep + 1);
      setStep(0);
      setChosen([]);
    }
  };

  api.handlers = {
    emptyEndsTrial: false,
    summarize,
    selectMeta: (it) => {
      if (!it) return {};
      if (it.id === "back") return { action: "back" };
      return { correct: wrong === null && it.id === `item-${target}`, step };
    },
    onSelect: (s) => {
      if (!api.session.inTrial || !s.item) return;
      const id = s.item.id;
      if (id === "back") {
        if (wrong !== null) {
          setWrong(null);
          api.announce("Back.");
        } else if (step > 0) {
          setStep(step - 1);
          setChosen((c) => c.slice(0, -1));
          api.announce("Back to the previous screen.");
        }
        return;
      }
      if (id === `item-${target}`) {
        setChosen((c) => [...c, s.item!.label ?? ""]);
        if (step + 1 >= screens.length) endTrial("completed", s.t);
        else setStep(step + 1);
        return;
      }
      errors.current++;
      setWrong(s.item.label ?? "");
      api.announce(`That opened ${s.item.label}, which is not what you were asked for. Use Back.`);
    },
    onSkip: () => api.session.inTrial && endTrial("abandoned", api.now()),
  };

  useEffect(() => {
    api.setItems(items);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, wrong, rep, chosen.length]);

  useEffect(() => {
    if (done) return;
    errors.current = 0;
    setWrong(null);
    api.setInstruction(`${nRep > 1 ? `Attempt ${rep + 1} of ${nRep}. ` : ""}${flow.cue}`);
    api.stimulusOnNextFrame({ trial: rep, task_flow: task, steps: screens.length });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rep, done]);

  if (done || !scr) return <p className="cue-box">Task complete.</p>;
  return (
    <>
      <p className="cue-box" style={{ top: 4, fontSize: 20, left: 760, transform: "none", maxWidth: 500 }}>
        {wrong !== null ? `Opened: ${wrong}` : flow.title[step]}
        {chosen.length > 0 && task !== "F1" && <span className="muted" style={{ display: "block", fontSize: 16 }}>So far: {chosen.join(" › ")}</span>}
      </p>
      {wrong !== null && (
        <p style={{ position: "absolute", left: 200, top: 300, fontSize: 26, maxWidth: 800 }}>
          This is not what you were asked to find. Select Back to return.
        </p>
      )}
      {items.map((it) => (
        <ItemButton key={`${rep}-${step}-${it.id}`} api={api} item={it} />
      ))}
    </>
  );
}
