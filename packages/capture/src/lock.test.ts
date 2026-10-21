import { describe, expect, it, vi } from "vitest";
import { lockConstraints, lockForLight, MAX_EXPOSURE_TIME } from "./lock";

// The G1 webcam (USB2.0 HD UVC WebCam): manual exposure 2.4..5000 (100 µs units) and manual white balance.
const G1_CAPS = {
  exposureMode: ["continuous", "manual"],
  exposureTime: { min: 2.44140625, max: 5000 },
  whiteBalanceMode: ["continuous", "manual"],
  colorTemperature: { min: 2800, max: 6500 },
};

function fakeTrack(caps: object, settings: object, apply = vi.fn(async () => undefined)) {
  return { track: { getCapabilities: () => caps, getSettings: () => settings, applyConstraints: apply } as unknown as MediaStreamTrack, apply };
}

describe("lockConstraints", () => {
  it("freezes exposure at no more than 33 ms and white balance at the current temperature", () => {
    const plan = lockConstraints(G1_CAPS, { exposureTime: 1250, colorTemperature: 4600 })!;
    expect(plan.set).toEqual({ exposureMode: "manual", exposureTime: MAX_EXPOSURE_TIME, whiteBalanceMode: "manual", colorTemperature: 4600 });
    expect(plan.lock).toEqual({ exposure: true, white_balance: true, exposure_time: MAX_EXPOSURE_TIME, error: null });
  });

  it("keeps a shorter exposure the camera already chose, inside the camera's range", () => {
    expect(lockConstraints(G1_CAPS, { exposureTime: 156.25 })!.lock.exposure_time).toBe(156.25);
    expect(lockConstraints({ ...G1_CAPS, exposureTime: { min: 200, max: 5000 } }, { exposureTime: 50 })!.lock.exposure_time).toBe(200);
  });

  it("locks only what the camera offers, and nothing on cameras without manual modes", () => {
    expect(lockConstraints({ exposureMode: ["continuous", "manual"], exposureTime: { min: 1, max: 1000 } }, {})!.lock).toMatchObject({ exposure: true, white_balance: false });
    expect(lockConstraints({ exposureMode: ["continuous"] }, { exposureTime: 100 })).toBeNull();
    expect(lockConstraints({}, {})).toBeNull(); // Safari and Firefox report no controls
  });
});

describe("lockForLight", () => {
  it("applies the lock, then restores continuous modes", async () => {
    const { track, apply } = fakeTrack(G1_CAPS, { exposureTime: 156.25, colorTemperature: 4600 });
    const { lock, restore } = await lockForLight(track);
    expect(lock).toMatchObject({ exposure: true, white_balance: true });
    expect(apply).toHaveBeenLastCalledWith({ advanced: [expect.objectContaining({ exposureMode: "manual" })] });
    await restore();
    expect(apply).toHaveBeenLastCalledWith({ advanced: [{ exposureMode: "continuous", whiteBalanceMode: "continuous" }] });
  });

  it("reports a refused lock instead of throwing, and restores nothing", async () => {
    const apply = vi.fn(async () => Promise.reject(new DOMException("not supported", "OverconstrainedError")));
    const { track } = fakeTrack(G1_CAPS, { colorTemperature: 4600 }, apply);
    const { lock, restore } = await lockForLight(track);
    expect(lock).toMatchObject({ exposure: false, white_balance: false });
    expect(lock!.error).toContain("not supported");
    await restore();
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it("does nothing on a camera without getCapabilities", async () => {
    const track = { getSettings: () => ({}), applyConstraints: vi.fn() } as unknown as MediaStreamTrack;
    expect((await lockForLight(track)).lock).toBeNull();
  });
});
