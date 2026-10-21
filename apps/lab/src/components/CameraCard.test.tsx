import { render, screen } from "@testing-library/react";
import { explain } from "@pulselens/explain";
import type { CameraDetails } from "@pulselens/types";
import { describe, expect, it } from "vitest";
import { CameraCard } from "./CameraCard";

// The G1 laptop session (ed0a0c434e62b495) as the Camera card received it, trimmed to the fields it shows.
const g1Laptop: CameraDetails = {
  channel: "desktop_browser", browser: "Brave 155", os: "Windows 19.0.0", ua_mobile: false,
  camera_label: "USB2.0 HD UVC WebCam (322e:202c)", device_id_hash: "97c95429db243bd6",
  settings: { width: 640, height: 480, frameRate: 30 }, capabilities: {}, native_modes: [], fps_median: 15.649,
  fps_jitter_ms: 6.99, clock_source: "captureTime", rvfc: true, resize_mode_supported: true, gyro: "absent",
  screen: {}, webgl_renderer: "Brave", webdriver: false, profile_claimed: "desktop_browser|ge27",
  profile_measured: "desktop_browser|lt20", noise_curve: null, fingerprint_pce: null,
};

const field = (k: Parameters<typeof explain>[0]) => screen.getByRole("group", { name: explain(k).title }).textContent;

describe("CameraCard with partial and mismatched details", () => {
  it("shows the measured profile and the claimed one when they differ", () => {
    render(<CameraCard details={g1Laptop} />);
    expect(field("field.profile")).toContain("desktop_browser|lt20 (claimed desktop_browser|ge27)");
    expect(field("field.fps")).toContain("15.6 fps, jitter 7.0 ms");
  });

  it("omits the claimed profile when it matches", () => {
    render(<CameraCard details={{ ...g1Laptop, profile_claimed: "desktop_browser|lt20" }} />);
    expect(field("field.profile")).not.toContain("claimed");
  });

  it("says when the camera reports no name or size yet, rather than showing blanks", () => {
    render(<CameraCard details={{ ...g1Laptop, camera_label: "", settings: {}, profile_measured: null, fps_jitter_ms: null }} />);
    expect(field("field.camera_label")).toContain("No name reported");
    expect(field("field.resolution")).toContain("Measuring");
    expect(field("field.profile")).toContain("Measuring");
    expect(field("field.fps")).toBe(`${explain("field.fps").title}15.6 fpsⓘ${explain("field.fps").text}`);
  });

  it.each([
    ["captureTime", "Camera capture time"],
    ["rvfc", "Video frame callback"],
    ["videoframe", "VideoFrame timestamp"],
    ["raf", "Animation frame (fallback)"],
  ] as const)("names the %s clock in plain words", (clock, words) => {
    render(<CameraCard details={{ ...g1Laptop, clock_source: clock }} />);
    expect(field("field.clock_source")).toContain(words);
  });
});
