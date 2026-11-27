import { memo, useEffect, useState, type ComponentType } from "react";
import type { TaskApi } from "./api";
import { IsoRingTask, SingleTargetTask } from "./PointingTasks";
import { GridSelectionTask, PhraseBoardTask } from "./SelectionTasks";
import { TypingTask } from "./TypingTask";
import { DragTask, SteeringTask, TrackingTask } from "./MotionTasks";
import { ScrollTask } from "./ScrollTask";
import { AdlTask } from "./AdlTasks";
import { loadAdl, loadPhrases, type AdlScreen } from "./stimuli";

function useData<T>(load: () => Promise<T>): T | null {
  const [d, setD] = useState<T | null>(null);
  useEffect(() => {
    let live = true;
    load().then((v) => live && setD(v));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return d;
}

function E2({ api }: { api: TaskApi }) {
  const phrases = useData(loadPhrases);
  return phrases ? <PhraseBoardTask api={api} phrases={phrases} /> : <p className="cue-box">Loading…</p>;
}

function Adl({ api }: { api: TaskApi }) {
  const layouts = useData<Record<string, AdlScreen[]>>(loadAdl);
  return layouts ? <AdlTask api={api} layouts={layouts} /> : <p className="cue-box">Loading…</p>;
}

type C = ComponentType<{ api: TaskApi }>;
const m = (c: C) => memo(c) as unknown as C;

export const TASK_COMPONENTS: Record<string, C> = {
  A1: m(SingleTargetTask),
  A5: m(SingleTargetTask),
  A2: m(IsoRingTask),
  A3: m(IsoRingTask),
  A4: m(GridSelectionTask),
  B1: m(SteeringTask),
  B2: m(TrackingTask),
  C1: m(ScrollTask),
  D1: m(DragTask),
  E1: m(TypingTask),
  E2: m(E2),
  F1: m(Adl),
  F2: m(Adl),
  F3: m(Adl),
  F4: m(Adl),
  F5: m(Adl),
  F6: m(Adl),
  F7: m(Adl),
};
