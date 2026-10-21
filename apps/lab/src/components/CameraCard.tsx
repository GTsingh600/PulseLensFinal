import type { CameraDetails } from "@pulselens/types";
import { explain, type ExplainerKey } from "@pulselens/explain";
import type { ReactNode } from "react";

/** One field with its value; tapping "ⓘ" opens the field's explainer. */
function Field({ k, children }: { k: ExplainerKey; children: ReactNode }) {
  const e = explain(k);
  return (
    <details className="field" aria-label={e.title}>
      <summary>
        <span className="field-title">{e.title}</span>
        <span className="field-value">{children}</span>
        <span className="info" aria-hidden="true">ⓘ</span>
      </summary>
      <p data-field="text">{e.text}</p>
    </details>
  );
}

const MEASURING = <em>Measuring…</em>;

const CHANNEL = { mobile_browser: "Mobile browser", desktop_browser: "Desktop browser" } as const;
const CLOCK = {
  captureTime: "Camera capture time",
  rvfc: "Video frame callback",
  videoframe: "VideoFrame timestamp",
  raf: "Animation frame (fallback)",
} as const;
const GYRO = { available: "Available", granted: "Allowed", denied: "Permission refused", absent: "Not present" } as const;

/** Basic Camera card for Lab Record (M1.6). The full card with modes and noise comes with M2.1. */
export function CameraCard({ details }: { details: CameraDetails }) {
  const s = details.settings as { width?: number; height?: number };
  return (
    <section className="card camera-card" aria-label="Camera details">
      <h3>Camera</h3>
      {details.browser.startsWith("Brave") && (
        <p className="notice warning" role="note">
          {explain("notice.brave").text}
        </p>
      )}
      <Field k="field.channel">{CHANNEL[details.channel]}</Field>
      <Field k="field.browser">
        {details.browser} on {details.os}
      </Field>
      <Field k="field.camera_label">{details.camera_label || <em>No name reported</em>}</Field>
      <Field k="field.resolution">{s.width && s.height ? `${s.width} × ${s.height}` : MEASURING}</Field>
      <Field k="field.fps">
        {details.fps_median === null
          ? MEASURING
          : `${details.fps_median.toFixed(1)} fps` +
            (details.fps_jitter_ms === null ? "" : `, jitter ${details.fps_jitter_ms.toFixed(1)} ms`)}
      </Field>
      <Field k="field.clock_source">{CLOCK[details.clock_source]}</Field>
      <Field k="field.gyro">{GYRO[details.gyro]}</Field>
      <Field k="field.profile">
        {details.profile_measured ?? MEASURING}
        {details.profile_claimed && details.profile_claimed !== details.profile_measured
          ? ` (claimed ${details.profile_claimed})`
          : ""}
      </Field>
    </section>
  );
}
