// The welcome card: what Concord is, the four steps, and a one-click way to try it with demo
// data. Shown until the user hides it (remembered in this browser); the guide has the rest.

import { useState } from "react";
import { runtimeApi, type DeviceDescriptor, type RuntimeSnapshot } from "../../sdk";
import { useHelp, useLoggedAction } from "../context";

const HIDDEN_KEY = "concord.welcome.hidden";

function readHidden(): boolean {
  try {
    return window.localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

function writeHidden(): void {
  try {
    window.localStorage.setItem(HIDDEN_KEY, "1");
  } catch {
    // storage unavailable (private window): the card simply shows again next time
  }
}

export const DEMO_DEVICE = "sim-a";

const STEPS = [
  ["Choose a data source", "Demo data, a recording, or your lab's live equipment."],
  ["Check the signal", "A green light means the data is arriving complete and on time."],
  ["Start a decoder", "It turns brain activity into intended actions, like moving a cursor."],
  ["Send to apps", "Only when you turn it on, and only to apps you allow."],
] as const;

export function Welcome({
  runtime,
  devices,
  onPick,
}: {
  runtime: RuntimeSnapshot | null;
  devices: DeviceDescriptor[];
  /** opens the source picker */
  onPick: () => void;
}) {
  const [hidden, setHidden] = useState(readHidden);
  const openHelp = useHelp();
  const action = useLoggedAction();
  if (hidden) return null;
  const connected = !!runtime?.device && runtime.state !== "idle";
  const demo = devices.find((d) => d.device_id === DEMO_DEVICE);
  const tryDemo = () => {
    if (demo && !connected) void action.run(() => runtimeApi.connect(DEMO_DEVICE));
    else onPick();
  };
  const hide = () => {
    writeHidden();
    setHidden(true);
  };
  return (
    <section className="welcome" aria-labelledby="welcome-title" data-testid="welcome">
      <div className="welcome-head">
        <div>
          <h2 id="welcome-title">Welcome to Concord</h2>
          <p>
            Concord reads brain signals, checks them, and can turn them into actions such as moving a cursor on a
            communication board. Work through the four steps below from top to bottom. It only ever listens: it never
            sends anything to a device.
          </p>
        </div>
        <button type="button" className="btn btn-quiet" onClick={hide} data-testid="welcome-hide">
          Hide this
        </button>
      </div>
      <ol className="welcome-steps">
        {STEPS.map(([t, d], i) => (
          <li key={t}>
            <span className="step" aria-hidden>
              {i + 1}
            </span>
            <div>
              <b>{t}</b>
              <span className="hint">{d}</span>
            </div>
          </li>
        ))}
      </ol>
      <div className="btn-row">
        {!connected && (
          <button type="button" className="btn btn-primary" disabled={action.busy} onClick={tryDemo} data-testid="welcome-demo">
            Try it with demo data
          </button>
        )}
        <button type="button" className="btn" onClick={() => openHelp("quick")} data-testid="welcome-guide">
          Read the 2-minute guide
        </button>
        <span className="hint">Demo data is made up by Concord: no equipment or brain data needed.</span>
      </div>
      {action.error && <p className="error-text">{action.error}</p>}
    </section>
  );
}

/** The always-visible use notice under the title bar. */
export function UseNotice() {
  const openHelp = useHelp();
  return (
    <div className="use-notice" role="note" data-testid="use-notice">
      <span>
        <b>Research preview.</b> Not a medical device. Not for clinical, diagnostic or commercial use. Not yet tested
        with real recording equipment or with people.
      </span>
      <button type="button" className="link" onClick={() => openHelp("safety")} data-testid="use-notice-more">
        Details
      </button>
    </div>
  );
}
