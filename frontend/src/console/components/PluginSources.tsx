// Source plugins (adapter SDK): installed packages, whether BrainOS accepts them, the devices
// they found, an options form generated from each plugin's option specs, and connect.
// Plugin code never runs in BrainOS itself: every plugin runs in its own process.

import { useEffect, useState } from "react";
import { runtimeApi, type DeviceDescriptor } from "../../sdk";
import { labApi, type OptionValue, type PluginDeviceInfo, type PluginInfo, type PluginOptionInfo, type PluginsStatus } from "../api";
import { useLog, useLoggedAction } from "../context";
import { modalityWords, shapeSummary, sourceKind } from "../wording";
import { Disclosure, fmt } from "./ui";

type Values = Record<string, string | boolean>;

function initialValues(options: PluginOptionInfo[]): Values {
  const v: Values = {};
  for (const o of options) {
    if (o.type === "bool") v[o.name] = o.default === true;
    else v[o.name] = o.default === null || o.default === undefined ? "" : String(o.default);
  }
  return v;
}

/** Only values that differ from the defaults are sent; the runtime validates and fills in the rest. */
export function changedOptions(options: PluginOptionInfo[], values: Values): Record<string, OptionValue> {
  const out: Record<string, OptionValue> = {};
  const defaults = initialValues(options);
  for (const o of options) {
    const v = values[o.name];
    if (v === undefined || v === defaults[o.name]) continue;
    if (typeof v === "string" && v.trim() === "" && !o.required) continue;
    out[o.name] = typeof v === "string" ? v.trim() : v;
  }
  return out;
}

function OptionsForm({
  options,
  values,
  onChange,
  idPrefix,
}: {
  options: PluginOptionInfo[];
  values: Values;
  onChange: (name: string, value: string | boolean) => void;
  idPrefix: string;
}) {
  return (
    <div className="form-grid" data-testid={`${idPrefix}-options`}>
      {options.map((o) => {
        const testId = `${idPrefix}-opt-${o.name}`;
        const v = values[o.name];
        if (o.type === "bool")
          return (
            <label key={o.name} className="check" title={o.description}>
              <input
                type="checkbox"
                checked={v === true}
                onChange={(e) => onChange(o.name, e.target.checked)}
                data-testid={testId}
              />
              {o.description}
            </label>
          );
        return (
          <label key={o.name} title={o.name}>
            {o.description}
            {o.required ? " (required)" : ""}
            {o.type === "choice" ? (
              <select value={String(v ?? "")} onChange={(e) => onChange(o.name, e.target.value)} data-testid={testId}>
                {!o.required && o.default === null && <option value="">Not set</option>}
                {o.choices.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            ) : (
              <input
                value={String(v ?? "")}
                inputMode={o.type === "str" ? undefined : "decimal"}
                onChange={(e) => onChange(o.name, e.target.value)}
                data-testid={testId}
              />
            )}
          </label>
        );
      })}
    </div>
  );
}

function PluginDevice({
  plugin,
  device,
  descriptor,
  activeId,
  busy,
  onConnect,
}: {
  plugin: PluginInfo;
  device: PluginDeviceInfo;
  descriptor: DeviceDescriptor | undefined;
  activeId: string | null;
  busy: boolean;
  onConnect: (values: Values) => void;
}) {
  const [values, setValues] = useState<Values>(() => initialValues(plugin.options));
  const active = device.device_id !== null && device.device_id === activeId;
  const sub = descriptor
    ? [sourceKind(descriptor)?.text, shapeSummary(descriptor), modalityWords(descriptor)].filter(Boolean).join(" · ")
    : device.description;
  const testId = device.device_id ?? `${plugin.name}-${device.device_key}`;
  return (
    <li className={`pick pick-wrap ${active ? "pick-active" : ""}`} data-testid={`plugin-device-${testId}`}>
      <div className="pick-text">
        <div className="pick-name">{device.display_name}</div>
        {sub && <div className="pick-sub">{sub}</div>}
        {device.reason && <div className="error-text">{device.reason}</div>}
      </div>
      <div className="pick-actions">
        {active ? (
          <span className="pick-current">Connected</span>
        ) : (
          device.device_id && (
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => onConnect(values)}
              data-testid={`plugin-connect-${device.device_id}`}
            >
              {activeId ? "Switch" : "Connect"}
            </button>
          )
        )}
      </div>
      {plugin.options.length > 0 && !active && device.device_id && (
        <Disclosure title="Options" className="inline pick-options" testId={`plugin-options-${device.device_id}`}>
          <OptionsForm
            options={plugin.options}
            values={values}
            idPrefix={device.device_id}
            onChange={(name, value) => setValues((v) => ({ ...v, [name]: value }))}
          />
        </Disclosure>
      )}
    </li>
  );
}

export function PluginSources({
  devices,
  activeId,
  onConnected,
  onSourcesChanged,
}: {
  /** registered plugin devices (from /devices) */
  devices: DeviceDescriptor[];
  activeId: string | null;
  onConnected: () => void;
  onSourcesChanged: () => void;
}) {
  const log = useLog();
  const action = useLoggedAction();
  const [status, setStatus] = useState<PluginsStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      labApi
        .plugins()
        .then((s) => {
          if (!alive) return;
          setStatus(s);
          setLoadError(null);
          // startup discovery runs in the background: look again until it has finished
          if (s.discovering || s.discovered_at_ns === null) setTimeout(load, 500);
        })
        .catch((e: unknown) => alive && setLoadError(e instanceof Error ? e.message : String(e)));
    load();
    return () => {
      alive = false;
    };
  }, []);

  const search = async () => {
    const s = await action.run(() => labApi.discoverPlugins());
    if (s) setStatus(s);
  };

  const connect = async (plugin: PluginInfo, device: PluginDeviceInfo, values: Values) => {
    const options = changedOptions(plugin.options, values);
    const ok = await action.run(async () => {
      const desc = await labApi.configurePlugin(plugin.name, device.device_key, options);
      onSourcesChanged();
      return activeId !== null ? runtimeApi.switch(desc.device_id) : runtimeApi.connect(desc.device_id);
    });
    if (ok) {
      log("info", `Plugin ${plugin.package ?? plugin.name}: ${device.display_name}`);
      onConnected();
    }
  };

  const plugins = status?.plugins ?? [];
  return (
    <div className="subsection" data-testid="plugin-sources">
      {/* M5-D: what "isolated" and "compatible" do and do not mean */}
      <p className="hint" data-testid="plugin-trust">
        Plugins are third-party code. Each runs in its own process, but with your user&apos;s permissions: it can read your
        files and use the network. &quot;Compatible&quot; means it follows the adapter contract, not that its code was
        reviewed. Install only plugins you trust.
      </p>
      {loadError && <p className="error-text">{loadError}</p>}
      {status?.error && <p className="error-text">Plugin search failed: {status.error}</p>}
      {action.error && (
        <p className="error-text" data-testid="plugin-error">
          {action.error}
        </p>
      )}
      {status && !plugins.length && !status.discovering && (
        <p className="value-muted" data-testid="no-plugins">
          No plugins installed. Install an adapter package into BrainOS's Python environment, then search again.
        </p>
      )}
      {plugins.length > 0 && (
        <ul className="pick-list" data-testid="plugin-list">
          {plugins.map((p) => {
            const usable = p.status === "compatible";
            const pkg = [p.package ?? p.name, p.version ?? p.package_version].filter(Boolean).join("@");
            return (
              <li key={p.name} className="plugin" data-testid={`plugin-${p.name}`}>
                <div className="pick-name">{p.display_name ?? p.name}</div>
                <div className="pick-sub" data-testid={`plugin-status-${p.name}`}>
                  {pkg} · {usable ? "compatible" : `${p.status === "load_error" ? "failed to load" : "rejected"}: ${p.reason ?? "unknown reason"}`}
                  {usable && p.ecosystem ? ` · ${p.ecosystem}` : ""}
                  {usable && p.network ? " · uses the network" : ""}
                </div>
                {usable && p.discovery_error && <p className="error-text">Device search failed: {p.discovery_error}</p>}
                {usable && p.devices.length > 0 && (
                  <ul className="pick-list">
                    {p.devices.map((d) => (
                      <PluginDevice
                        key={d.device_key}
                        plugin={p}
                        device={d}
                        descriptor={devices.find((x) => x.device_id === d.device_id)}
                        activeId={activeId}
                        busy={action.busy}
                        onConnect={(values) => connect(p, d, values)}
                      />
                    ))}
                  </ul>
                )}
                {usable && !p.devices.length && !p.discovery_error && <p className="hint">No devices found.</p>}
              </li>
            );
          })}
        </ul>
      )}
      <div className="btn-row">
        <button type="button" className="btn btn-quiet" disabled={action.busy} onClick={search} data-testid="plugins-search">
          {status?.discovering || action.busy ? "Searching…" : "Search again"}
        </button>
        {status?.discovered_at_ns ? (
          <span className="hint">
            Last search {fmt.ago(status.discovered_at_ns)} · adapter SDK {status.host_api_version}
          </span>
        ) : null}
      </div>
    </div>
  );
}
