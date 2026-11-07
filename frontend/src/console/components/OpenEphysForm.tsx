// Register an Open Ephys GUI "ZMQ Interface" plugin endpoint as a read-only source.

import { useState } from "react";
import { labApi, type OpenEphysUnit } from "../api";
import { useAction } from "../hooks";
import { Panel } from "./ui";

const UNITS: OpenEphysUnit[] = ["unknown", "uV", "mV", "V"];

export function OpenEphysForm({
  onSourcesChanged,
  notify,
}: {
  onSourcesChanged: () => void;
  notify: (text: string) => void;
}) {
  const [host, setHost] = useState("127.0.0.1");
  const [port, setPort] = useState("5556");
  const [unit, setUnit] = useState<OpenEphysUnit>("unknown");
  const action = useAction();
  const portNum = Number(port);
  const portOk = Number.isInteger(portNum) && portNum >= 1 && portNum <= 65534;

  const register = async () => {
    const desc = await action.run(() => labApi.openEphysRegister({ host: host.trim(), data_port: portNum, unit }));
    if (!desc) return;
    notify(`Registered ${desc.device_id} — connect it from Devices & sources`);
    onSourcesChanged();
  };

  return (
    <Panel title="Open Ephys · ZMQ Interface" testId="openephys-form">
      <div className="form-grid">
        <label>
          host
          <input value={host} onChange={(e) => setHost(e.target.value)} data-testid="oe-host" />
        </label>
        <label>
          data port
          <input
            value={port}
            inputMode="numeric"
            onChange={(e) => setPort(e.target.value)}
            data-testid="oe-port"
            aria-invalid={!portOk}
          />
        </label>
        <label>
          sample unit
          <select value={unit} onChange={(e) => setUnit(e.target.value as OpenEphysUnit)} data-testid="oe-unit">
            {UNITS.map((u) => (
              <option key={u} value={u}>
                {u === "unknown" ? "unknown (pass through unscaled)" : u}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="btn-row">
        <button
          className="btn btn-primary"
          disabled={action.busy || !portOk || !host.trim()}
          onClick={register}
          data-testid="oe-register"
        >
          Register Open Ephys source
        </button>
      </div>
      {action.error && (
        <div className="alert" data-testid="oe-error">
          {action.error}
        </div>
      )}
      <p className="muted small">
        The ZMQ Interface plugin does not transmit units. With <b>unknown</b>, samples are passed through unscaled and
        labelled <code>arbitrary</code>; choose the unit configured in the GUI to have them converted to µV. Heartbeats
        go to port {portOk ? portNum + 1 : "data port + 1"}. Registering does not connect — BrainOS only subscribes
        (read-only) once you connect the source.
      </p>
    </Panel>
  );
}
