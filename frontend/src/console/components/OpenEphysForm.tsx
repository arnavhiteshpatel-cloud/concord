// Register an Open Ephys GUI "ZMQ Interface" plugin endpoint as a read-only source.

import { useState } from "react";
import { labApi, type OpenEphysUnit } from "../api";
import { useLog, useLoggedAction } from "../context";

const UNITS: OpenEphysUnit[] = ["unknown", "uV", "mV", "V"];

export function OpenEphysForm({ onSourcesChanged }: { onSourcesChanged: () => void }) {
  const log = useLog();
  const [host, setHost] = useState("127.0.0.1");
  const [port, setPort] = useState("5556");
  const [unit, setUnit] = useState<OpenEphysUnit>("unknown");
  const action = useLoggedAction();
  const portNum = Number(port);
  const portOk = Number.isInteger(portNum) && portNum >= 1 && portNum <= 65534;

  const register = async () => {
    const desc = await action.run(() => labApi.openEphysRegister({ host: host.trim(), data_port: portNum, unit }));
    if (!desc) return;
    log("info", `Registered ${desc.display_name ?? desc.device_id}`);
    onSourcesChanged();
  };

  return (
    <div className="subsection" data-testid="openephys-form">
      <div className="form-grid">
        <label>
          Host
          <input value={host} onChange={(e) => setHost(e.target.value)} data-testid="oe-host" />
        </label>
        <label>
          Data port
          <input
            value={port}
            inputMode="numeric"
            onChange={(e) => setPort(e.target.value)}
            data-testid="oe-port"
            aria-invalid={!portOk}
          />
        </label>
        <label>
          Sample unit
          <select value={unit} onChange={(e) => setUnit(e.target.value as OpenEphysUnit)} data-testid="oe-unit">
            {UNITS.map((u) => (
              <option key={u} value={u}>
                {u === "unknown" ? "Unknown (pass through unscaled)" : u}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="btn-row">
        <button
          type="button"
          className="btn btn-primary"
          disabled={action.busy || !portOk || !host.trim()}
          onClick={register}
          data-testid="oe-register"
        >
          Add source
        </button>
      </div>
      {action.error && (
        <p className="error-text" data-testid="oe-error">
          {action.error}
        </p>
      )}
      <p className="hint">
        The ZMQ Interface plugin does not transmit units. With <b>Unknown</b>, samples are passed through unscaled and
        labelled arbitrary; choose the unit configured in the GUI to have them converted to µV. Heartbeats go to port{" "}
        {portOk ? portNum + 1 : "data port + 1"}. Adding a source does not connect it.
      </p>
    </div>
  );
}
