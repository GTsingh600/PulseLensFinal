import { CaptureSession, startTap, type CaptureState } from "@pulselens/capture";
import { explainMaybe, type ExplainerKey } from "@pulselens/explain";
import type { RecordingLabel, Stage } from "@pulselens/types";
import { useEffect, useRef, useState } from "react";
import { CameraCard } from "../components/CameraCard";
import { ExplainPanel } from "../components/ExplainPanel";
import { OperatorForm } from "./OperatorForm";

const STAGE_KEYS: Record<Stage, ExplainerKey> = {
  camera: "stage.camera",
  coach: "stage.coach",
  plan: "stage.plan",
  pulses: "stage.pulses",
  face: "stage.face",
  decide: "stage.decide",
};

const promptText = (key: string) => explainMaybe(key)?.text ?? "";

/**
 * Lab Record, minimal (M1.6): operator form → hand to volunteer → camera, coach and light suite with the stage
 * explainer and a basic Camera card → a labelled bundle uploaded. The superset protocol is M2.2.
 */
export function RecordPage() {
  const [label, setLabel] = useState<RecordingLabel | null>(null);
  const [state, setState] = useState<CaptureState | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const session = useRef<CaptureSession | null>(null);

  useEffect(
    () => () => {
      const s = session.current;
      if (s && s.state.phase !== "done" && s.state.phase !== "error") void s.fail("Left the Record page.");
    },
    [],
  );

  const start = () => {
    const tap = startTap(); // first, inside the click: fullscreen and motion permission need the gesture
    const s = new CaptureSession({
      video: video.current!,
      product: "lab",
      mode: "superset",
      role: "lab",
      label,
      promptText,
      onChange: setState,
    });
    session.current = s;
    void tap.then((r) => s.start(r));
  };

  const reset = () => {
    session.current = null;
    setState(null);
    setLabel(null);
  };

  if (!label) {
    return (
      <main>
        <h1>Record</h1>
        <OperatorForm onSubmit={setLabel} />
      </main>
    );
  }

  if (state?.phase === "done") {
    return (
      <main>
        <section className="card" aria-label="Recording summary">
          <h2>Recording saved</h2>
          <p>
            Session <code>{state.sessionId}</code> for {label.person} on {label.device}: {state.uploaded} frames uploaded,{" "}
            {state.dropped} dropped, {state.acksOk} of {state.pulses} light pulses answered.
          </p>
          <button type="button" onClick={reset}>
            Record another
          </button>
        </section>
      </main>
    );
  }

  const stageKey = state?.stage ? STAGE_KEYS[state.stage] : null;
  const latestTips = state?.stage === "coach" ? (state.coach.at(-1)?.tips ?? []) : [];
  const running = state && state.phase !== "idle";

  return (
    <main className="record">
      {!running && (
        <section className="card handover">
          <h2>Hand the device to the volunteer</h2>
          <p>{promptText("prompt.start")}</p>
          <p className="notice">{promptText("notice.flash")}</p>
          <button type="button" className="primary" onClick={start}>
            Start
          </button>
        </section>
      )}
      {state?.phase === "error" && (
        <section className="card error-card" role="alert">
          <h2>Recording stopped</h2>
          <p>{state.error}</p>
          <button type="button" onClick={reset}>
            Start over
          </button>
        </section>
      )}
      <div className="stage-layout">
        <video ref={video} className="preview" muted playsInline />
        <div className="stage-side">
          {stageKey ? <ExplainPanel k={stageKey} /> : running && state.phase !== "error" && <p>Starting the camera…</p>}
          {state?.promptKey && state.stage !== "coach" && (
            <p className="prompt" data-testid="prompt">
              {promptText(state.promptKey)}
            </p>
          )}
          {latestTips.length > 0 && (
            <ul className="tips" aria-label="Tips">
              {latestTips.map((t) => (
                <li key={t}>{promptText(t)}</li>
              ))}
            </ul>
          )}
          {running && (
            <p className="progress">
              {state.frames} frames captured, {state.uploaded} uploaded
              {state.pulses ? `, ${state.acksOk} of ${state.pulses} pulses answered` : ""}
            </p>
          )}
        </div>
      </div>
      {state?.details && <CameraCard details={state.details} />}
    </main>
  );
}
