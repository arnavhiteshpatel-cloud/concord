// The session log is written from many places (rows, sheets, Advanced). A context keeps the
// writer out of every prop list.

import { createContext, useContext } from "react";
import { useAction, type Action } from "./hooks";
import type { Tone } from "./wording";

export type LogWriter = (tone: Tone, text: string) => void;

export const LogContext = createContext<LogWriter>(() => {});

export const useLog = (): LogWriter => useContext(LogContext);

/** Opens the in-app guide, optionally at one of its sections (see components/Guide.tsx). */
export type HelpOpener = (section?: string) => void;

export const HelpContext = createContext<HelpOpener>(() => {});

export const useHelp = (): HelpOpener => useContext(HelpContext);

/** useAction whose refusals also go to the session log, verbatim. */
export function useLoggedAction(): Action {
  const log = useLog();
  // a refused request is a technical message: neutral, not an alarm colour
  return useAction((text) => log("info", `Refused: ${text}`));
}
