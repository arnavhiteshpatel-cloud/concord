// Communication board — settings for the caregiver / experimenter (the participant view itself
// needs no keyboard or mouse). Every field changes how the board behaves; nothing here
// configures the runtime, the decoder or the command router.

import type { Capability } from "../../sdk";
import { SPEECH_LABEL } from "./feedback";
import { METHOD_LABEL, METHOD_ORDER, availableMethods, type Method, type MethodChoice } from "./methods";
import { LIMITS, type BoardSettings } from "./settings";

export function SettingsPanel({
  settings,
  granted,
  method,
  speechAvailable,
  wordsError,
  onChange,
  onClearHistory,
  onClose,
}: {
  settings: BoardSettings;
  granted: Capability[];
  method: Method | null;
  speechAvailable: boolean;
  wordsError: string | null;
  onChange: (s: BoardSettings) => void;
  onClearHistory: () => void;
  onClose: () => void;
}) {
  const avail = availableMethods(granted);
  const set = <K extends keyof BoardSettings>(k: K, v: BoardSettings[K]) => onChange({ ...settings, [k]: v });
  const numberField = (k: "dwellMs" | "scanIntervalMs" | "clickRefractoryMs" | "confirmMs" | "gridN", label: string, title: string) => (
    <label title={title}>
      {label}
      <input
        type="number"
        min={LIMITS[k][0]}
        max={LIMITS[k][1]}
        value={settings[k]}
        onChange={(e) => {
          const v = Number(e.target.value);
          if (Number.isFinite(v)) set(k, Math.min(LIMITS[k][1], Math.max(LIMITS[k][0], Math.round(v))));
        }}
        data-testid={`setting-${k}`}
      />
    </label>
  );
  return (
    <div className="board-settings" role="dialog" aria-label="Board settings" data-testid="board-settings">
      <div className="settings-head">
        <h2>Board settings</h2>
        <button type="button" onClick={onClose} data-testid="board-settings-close">
          Close
        </button>
      </div>
      <p className="settings-note">
        For the caregiver or experimenter. Cursor speed and smoothing are not set here: the operator maps decoder output to
        commands in Concord.
      </p>
      <fieldset>
        <legend>Input method</legend>
        <label>
          <input type="radio" name="method" checked={settings.method === "auto"} onChange={() => set("method", "auto")} data-testid="method-auto" />
          Automatic{method ? ` (now: ${METHOD_LABEL[method]})` : " (nothing available now)"}
        </label>
        {METHOD_ORDER.map((m) => (
          <label key={m} className={avail.includes(m) ? "" : "unavailable"}>
            <input
              type="radio"
              name="method"
              checked={settings.method === m}
              disabled={!avail.includes(m)}
              onChange={() => set("method", m as MethodChoice)}
              data-testid={`method-${m}`}
            />
            {METHOD_LABEL[m]}
            {!avail.includes(m) && <small> — not offered by the current source</small>}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Layout</legend>
        <label>
          Layout
          <select value={settings.layout} onChange={(e) => set("layout", e.target.value as BoardSettings["layout"])} data-testid="setting-layout">
            <option value="communication">Phrases and letters</option>
            <option value="grid">Task grid (N × N words)</option>
          </select>
        </label>
        {settings.layout === "grid" ? (
          <>
            {numberField("gridN", "Grid size N", "N × N tiles over a square workspace")}
            <label title="A text file with one word or phrase per line">
              Word list URL
              <input
                type="text"
                value={settings.wordsUrl ?? ""}
                placeholder="built-in core vocabulary"
                onChange={(e) => set("wordsUrl", e.target.value.trim() || null)}
                data-testid="setting-wordsUrl"
              />
            </label>
            {wordsError && <p className="settings-error">{wordsError}</p>}
          </>
        ) : (
          <label>
            Tile size (phrase page)
            <select value={settings.tileSize} onChange={(e) => set("tileSize", e.target.value as BoardSettings["tileSize"])} data-testid="setting-tileSize">
              <option value="large">Large (3 × 3)</option>
              <option value="standard">Standard (4 × 4)</option>
              <option value="small">Small (5 × 5)</option>
            </select>
          </label>
        )}
        <label>
          Text size
          <input
            type="range"
            min={LIMITS.textScale[0]}
            max={LIMITS.textScale[1]}
            step={0.05}
            value={settings.textScale}
            onChange={(e) => set("textScale", Number(e.target.value))}
            data-testid="setting-textScale"
          />
          <span>{Math.round(settings.textScale * 100)}%</span>
        </label>
      </fieldset>
      <fieldset>
        <legend>Timing</legend>
        {numberField("dwellMs", "Dwell time (ms)", "Pointer with dwell selection: time resting on a tile that chooses it")}
        {numberField("scanIntervalMs", "Scan interval (ms)", "Scanning: time each tile or row stays highlighted")}
        <label>
          Scan pattern
          <select value={settings.scanPattern} onChange={(e) => set("scanPattern", e.target.value as BoardSettings["scanPattern"])} data-testid="setting-scanPattern">
            <option value="linear">Tile by tile</option>
            <option value="row_column">Row, then column</option>
          </select>
        </label>
        {numberField(
          "clickRefractoryMs",
          "Click / switch debounce (ms)",
          "A selection within this time of the previous one is ignored (one click selects once)",
        )}
        <label>
          Confirmation
          <select value={settings.confirm} onChange={(e) => set("confirm", e.target.value as BoardSettings["confirm"])} data-testid="setting-confirm">
            <option value="none">None: choose at once</option>
            <option value="repeat">Select the same tile twice</option>
          </select>
        </label>
        {settings.confirm === "repeat" && numberField("confirmMs", "Confirm within (ms)", "Time allowed for the second selection")}
      </fieldset>
      <fieldset>
        <legend>Feedback and speech</legend>
        <label className="check">
          <input type="checkbox" checked={settings.audioTick} onChange={(e) => set("audioTick", e.target.checked)} data-testid="setting-audioTick" />
          Audio tick on every selection
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={settings.speech}
            disabled={!speechAvailable}
            onChange={(e) => set("speech", e.target.checked)}
            data-testid="setting-speech"
          />
          Read the message aloud on Speak — {SPEECH_LABEL}
          {!speechAvailable && <small> (not available in this browser)</small>}
        </label>
        {speechAvailable && settings.speech && (
          <label>
            Speech rate
            <input
              type="range"
              min={LIMITS.speechRate[0]}
              max={LIMITS.speechRate[1]}
              step={0.1}
              value={settings.speechRate}
              onChange={(e) => set("speechRate", Number(e.target.value))}
            />
            <span>{settings.speechRate.toFixed(1)}×</span>
          </label>
        )}
      </fieldset>
      <div className="settings-actions">
        <button type="button" onClick={onClearHistory} data-testid="board-clear-history">
          Clear history
        </button>
      </div>
    </div>
  );
}
