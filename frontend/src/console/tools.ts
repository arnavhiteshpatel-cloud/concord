// The "More tools" area: every tool, its plain name, what it does and when to use it. Shared by
// the tools area on the session screen and the in-app guide, so both always say the same thing.

export interface ToolInfo {
  /** test id of the tool card (and `${id}-toggle` for its Show/Hide button) */
  id: string;
  title: string;
  /** one sentence: what the tool shows or does */
  what: string;
  /** when you would open it */
  when: string;
}

export interface ToolGroup {
  title: string;
  tools: ToolInfo[];
}

export const TOOL_GROUPS: ToolGroup[] = [
  {
    title: "Watch what is happening",
    tools: [
      {
        id: "adv-board",
        title: "Participant screen preview",
        what: "A live copy of the communication board, the screen the person using the BCI sees.",
        when: "Watch the board from this screen. For the person using it, use Open participant screen instead.",
      },
      {
        id: "adv-events",
        title: "Live message feed",
        what: "Every message passing through Concord, as it happens, each labelled with where it came from.",
        when: "When you want to see exactly what a source is sending.",
      },
      {
        id: "adv-acquisition",
        title: "Source details",
        what: "Everything known about the connected source: the file being played, live stream counters, or simulator readings.",
        when: "When you want more than the summary in step 1.",
      },
      {
        id: "adv-pipeline",
        title: "Decoder details",
        what: "The full settings and counters of the running decoder: processing steps, timing and dropped data.",
        when: "When the decoder behaves unexpectedly.",
      },
    ],
  },
  {
    title: "Record and manage data",
    tools: [
      {
        id: "adv-recording",
        title: "Record data",
        what: "Save the data from the connected source to a file, and see earlier recordings.",
        when: "To keep a copy of a session, or to play it back later as a source.",
      },
      {
        id: "adv-storage",
        title: "Saved data",
        what: "What Concord has stored on this computer, how much space it uses, and how to delete it.",
        when: "To free up space or remove recordings you no longer need.",
      },
    ],
  },
  {
    title: "Apps",
    tools: [
      {
        id: "adv-apps",
        title: "Connected apps",
        what: "The apps connected to Concord and what each one asked for and was given.",
        when: "When an app does not respond to the decoder.",
      },
    ],
  },
  {
    title: "Check and troubleshoot",
    tools: [
      {
        id: "adv-diagnostics",
        title: "Health check",
        what: "Speed, delays, dropped data and recent errors inside Concord.",
        when: "When something seems slow, stuck or incomplete.",
      },
      {
        id: "adv-contract",
        title: "Source capabilities",
        what: "What each available source says it can provide, for example raw signals, pointer movement or selections.",
        when: "To see why an app or decoder cannot use a source.",
      },
      {
        id: "adv-compat",
        title: "Compatibility",
        what: "Which recording systems and formats Concord has been tested with, and how far each was tested.",
        when: "Before using Concord with your own equipment.",
      },
      {
        id: "adv-tests",
        title: "Self-tests",
        what: "The results of Concord's own automated tests, when this copy was built from source.",
        when: "To confirm a developer build passed its checks.",
      },
      {
        id: "adv-support",
        title: "Support report",
        what: "A file describing your setup and recent errors, without your recordings or notes.",
        when: "When asking someone for help with a problem.",
      },
    ],
  },
];

/** Shown only while a built-in simulated profile is connected. */
export const SIMULATOR_TOOL: ToolInfo = {
  id: "adv-simulator",
  title: "Simulator controls",
  what: "Steer the simulated device by hand: drag to move the pointer, click to select, or add faults such as dropouts.",
  when: "To practise with the participant screen, or to see how Concord reacts to problems.",
};
