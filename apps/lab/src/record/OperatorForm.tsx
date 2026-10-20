import { attackToolValues, type AttackTool, type RecordingLabel } from "@pulselens/types";
import { useId, useState, type FormEvent, type ReactNode } from "react";

const TOOL_NAMES: Record<AttackTool, string> = {
  screen_replay: "Screen replay (video on a phone held to the camera)",
  premade_injection: "Pre-made injection (OBS virtual camera)",
  liveportrait: "Single-photo fake (LivePortrait)",
  liveswap: "Live face-swap (Deep-Live-Cam)",
  source_switch: "Source switch (swap turned on after the pulses)",
  emulator: "Emulator injection (Android Studio)",
};

type Kind = "" | "genuine" | "attack";
type Errors = Partial<Record<keyof RecordingLabel, string>>;

function validate(f: { person: string; device: string; consent: string; kind: Kind; tool: "" | AttackTool }): Errors {
  const e: Errors = {};
  if (!/^P\d{2,3}$/.test(f.person)) e.person = "Use the pseudonymous code like P01, never a name.";
  if (!f.device.trim()) e.device = "Enter the device code from the device sheet, e.g. D01.";
  if (!f.kind) e.kind = "Pick genuine or attack.";
  if (f.kind === "attack" && !f.tool) e.tool = "Pick the attack tool.";
  if (!f.consent.trim()) e.consent_ref = "Every session needs a signed consent form reference.";
  return e;
}

function Row({ id, label, error, children }: { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <div className="row">
      <label htmlFor={id}>{label}</label>
      {children}
      {error && <span className="error">{error}</span>}
    </div>
  );
}

/** Lab Record step 1 (SPEC 13.3): who, on what device, in which light, genuine or attack. */
export function OperatorForm({ onSubmit }: { onSubmit: (label: RecordingLabel) => void }) {
  const id = useId();
  const [person, setPerson] = useState("");
  const [device, setDevice] = useState("");
  const [light, setLight] = useState<"normal" | "dim">("normal");
  const [kind, setKind] = useState<Kind>("");
  const [tool, setTool] = useState<"" | AttackTool>("");
  const [consent, setConsent] = useState("");
  const [errors, setErrors] = useState<Errors>({});

  const submit = (ev: FormEvent) => {
    ev.preventDefault();
    const p = person.trim().toUpperCase();
    const found = validate({ person: p, device, consent, kind, tool });
    setErrors(found);
    if (Object.keys(found).length || !kind) return;
    onSubmit({
      person: p, device: device.trim(), light, kind, tool: kind === "attack" ? (tool as AttackTool) : null,
      consent_ref: consent.trim(),
    });
  };

  return (
    <form className="card operator-form" onSubmit={submit} noValidate>
      <h2>Operator form</h2>
      <Row id={`${id}-person`} label="Person code" error={errors.person}>
        <input id={`${id}-person`} value={person} onChange={(e) => setPerson(e.target.value)} placeholder="P01" autoComplete="off" />
      </Row>
      <Row id={`${id}-device`} label="Device code" error={errors.device}>
        <input id={`${id}-device`} value={device} onChange={(e) => setDevice(e.target.value)} placeholder="D01" autoComplete="off" />
      </Row>
      <Row id={`${id}-light`} label="Light">
        <select id={`${id}-light`} value={light} onChange={(e) => setLight(e.target.value as "normal" | "dim")}>
          <option value="normal">Normal</option>
          <option value="dim">Dim</option>
        </select>
      </Row>
      <fieldset>
        <legend>Session kind</legend>
        {(["genuine", "attack"] as const).map((k) => (
          <span className="inline" key={k}>
            <input id={`${id}-${k}`} type="radio" name="kind" checked={kind === k} onChange={() => setKind(k)} />
            <label htmlFor={`${id}-${k}`}>{k === "genuine" ? "Genuine" : "Attack"}</label>
          </span>
        ))}
        {errors.kind && <span className="error">{errors.kind}</span>}
      </fieldset>
      {kind === "attack" && (
        <Row id={`${id}-tool`} label="Attack tool" error={errors.tool}>
          <select id={`${id}-tool`} value={tool} onChange={(e) => setTool(e.target.value as AttackTool)}>
            <option value="">Choose…</option>
            {attackToolValues.map((t) => (
              <option key={t} value={t}>
                {TOOL_NAMES[t]}
              </option>
            ))}
          </select>
        </Row>
      )}
      <Row id={`${id}-consent`} label="Consent reference" error={errors.consent_ref}>
        <input id={`${id}-consent`} value={consent} onChange={(e) => setConsent(e.target.value)} placeholder="C-01" autoComplete="off" />
      </Row>
      <button type="submit">Continue</button>
    </form>
  );
}
