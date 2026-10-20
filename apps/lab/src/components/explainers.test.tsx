import { render, screen, within } from "@testing-library/react";
import type { CameraDetails } from "@pulselens/types";
import { explain } from "@pulselens/explain";
import { describe, expect, it } from "vitest";
import { CameraCard } from "./CameraCard";
import { ExplainPanel } from "./ExplainPanel";

const details: CameraDetails = {
  channel: "desktop_browser", browser: "Chrome 129", os: "Windows", ua_mobile: false, camera_label: "HD Webcam",
  device_id_hash: "0123456789abcdef", settings: { width: 640, height: 480, frameRate: 30 }, capabilities: {},
  native_modes: [], fps_median: 29.6, fps_jitter_ms: 2.4, clock_source: "captureTime", rvfc: true,
  resize_mode_supported: true, gyro: "absent", screen: {}, webgl_renderer: null, webdriver: false,
  profile_claimed: "desktop_browser|ge27", profile_measured: "desktop_browser|ge27", noise_curve: null, fingerprint_pce: null,
};

describe("ExplainPanel", () => {
  it("shows the stage explainer word for word", () => {
    render(<ExplainPanel k="stage.pulses" />);
    const panel = screen.getByRole("region", { name: "Stage explanation" });
    const e = explain("stage.pulses");
    expect(within(panel).getByRole("heading").textContent).toBe(e.title);
    expect(panel.querySelector("[data-field=what]")!.textContent).toBe(e.what);
    expect(panel.querySelector("[data-field=why]")!.textContent).toBe(e.why);
    expect(panel.querySelector("[data-field=read]")!.textContent).toBe(e.read);
  });
});

describe("CameraCard (basic)", () => {
  it("shows measured values with each field's explainer", () => {
    render(<CameraCard details={details} />);
    const fps = screen.getByRole("group", { name: explain("field.fps").title });
    expect(fps.textContent).toContain("29.6 fps");
    expect(fps.querySelector("[data-field=text]")!.textContent).toBe(explain("field.fps").text);
    expect(screen.getByRole("group", { name: explain("field.resolution").title }).textContent).toContain("640 × 480");
    expect(screen.getByRole("group", { name: explain("field.gyro").title }).textContent).toContain("Not present");
  });

  it("says a value is still being measured instead of inventing one", () => {
    render(<CameraCard details={{ ...details, fps_median: null, fps_jitter_ms: null }} />);
    expect(screen.getByRole("group", { name: explain("field.fps").title }).textContent).toContain("Measuring");
  });
});
