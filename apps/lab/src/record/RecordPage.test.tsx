import { act, fireEvent, render, screen } from "@testing-library/react";
import { explain } from "@pulselens/explain";
import type { CaptureState } from "@pulselens/capture";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sessions: FakeSession[] = [];

class FakeSession {
  opts: { onChange: (s: CaptureState) => void; label: unknown; mode: string; role: string };
  start = vi.fn(async () => undefined);
  fail = vi.fn(async () => undefined);
  constructor(opts: FakeSession["opts"]) {
    this.opts = opts;
    sessions.push(this);
  }
  state: CaptureState = { ...IDLE };
  emit(patch: Partial<CaptureState>) {
    this.state = { ...IDLE, ...patch };
    act(() => this.opts.onChange(this.state));
  }
}

const IDLE: CaptureState = {
  phase: "idle", sessionId: null, stage: null, promptKey: null, channel: null, details: null, coach: [], frames: 0,
  uploaded: 0, dropped: 0, pulses: 0, acksOk: 0, doneKey: null, error: null,
};

vi.mock("@pulselens/capture", () => ({
  CaptureSession: FakeSession,
  startTap: vi.fn(async () => ({ fullscreen: false, wakeLock: false, orientationLocked: false, motionPermission: "not-needed" })),
}));

const { RecordPage } = await import("./RecordPage");

function fillForm() {
  const fill = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fill("Person code", "P01");
  fill("Device code", "D01");
  fill("Consent reference", "C-01");
  fireEvent.click(screen.getByLabelText("Genuine"));
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
}

async function started() {
  render(<RecordPage />);
  fillForm();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Start" })));
  return sessions.at(-1)!;
}

beforeEach(() => {
  sessions.length = 0;
});

describe("RecordPage", () => {
  it("goes from the operator form to the hand-over screen with the start prompt and flash notice", () => {
    render(<RecordPage />);
    fillForm();
    expect(screen.getByRole("heading", { name: "Hand the device to the volunteer" })).toBeTruthy();
    expect(screen.getByText(explain("prompt.start").text!)).toBeTruthy();
    expect(screen.getByText(explain("notice.flash").text!)).toBeTruthy();
  });

  it("starts a labelled Lab capture session from the Start tap", async () => {
    const s = await started();
    expect(s.opts).toMatchObject({ mode: "superset", role: "lab", label: { person: "P01", device: "D01", kind: "genuine" } });
    await vi.waitFor(() => expect(s.start).toHaveBeenCalledWith(expect.objectContaining({ motionPermission: "not-needed" })));
  });

  it("shows the stage explainer, the prompt and progress while running", async () => {
    const s = await started();
    s.emit({ phase: "running", stage: "pulses", promptKey: "prompt.start", frames: 120, uploaded: 90, pulses: 3, acksOk: 3 });
    expect(screen.getByRole("region", { name: "Stage explanation" }).textContent).toContain(explain("stage.pulses").title);
    expect(screen.getByTestId("prompt").textContent).toBe(explain("prompt.start").text);
    expect(screen.getByText(/120 frames captured, 90 uploaded, 3 of 3 pulses answered/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Start" })).toBeNull();
  });

  it("shows coaching tips instead of the prompt during the coach stage", async () => {
    const s = await started();
    s.emit({ phase: "running", stage: "coach", promptKey: "prompt.coach.closer", coach: [{ round: 1, tips: ["prompt.coach.closer"], metrics: {} }] as never });
    expect(screen.getByRole("list", { name: "Tips" }).textContent).toBe(explain("prompt.coach.closer").text);
    expect(screen.queryByTestId("prompt")).toBeNull();
  });

  it("shows the error and starts over from the form", async () => {
    const s = await started();
    s.emit({ phase: "error", error: "Connection to the server closed." });
    expect(screen.getByRole("alert").textContent).toContain("Connection to the server closed.");
    fireEvent.click(screen.getByRole("button", { name: "Start over" }));
    expect(screen.getByRole("heading", { name: "Record" })).toBeTruthy();
  });

  it("ends on a summary with the session id and counts, and can record another", async () => {
    const s = await started();
    s.emit({ phase: "done", sessionId: "ed0a0c434e62b495", uploaded: 366, dropped: 0, pulses: 10, acksOk: 10 });
    const summary = screen.getByRole("region", { name: "Recording summary" });
    expect(summary.textContent).toContain("ed0a0c434e62b495");
    expect(summary.textContent).toContain("366 frames uploaded, 0 dropped, 10 of 10 light pulses answered");
    fireEvent.click(screen.getByRole("button", { name: "Record another" }));
    expect(screen.getByRole("heading", { name: "Record" })).toBeTruthy();
  });
});

describe("RecordPage unmount", () => {
  it("fails a running session with a reason when the page unmounts", async () => {
    const view = render(<RecordPage />);
    fillForm();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Start" })));
    const s = sessions.at(-1)!;
    s.emit({ phase: "running", stage: "camera" });
    view.unmount();
    expect(s.fail).toHaveBeenCalledWith("Left the Record page.");
  });

  // After "Recording saved" there is nothing to stop, but leaving the page still calls fail(), which logs
  // "Capture session failed" and flips a finished session to the error phase.
  it("does not fail a session that already finished", async () => {
    const view = render(<RecordPage />);
    fillForm();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Start" })));
    const s = sessions.at(-1)!;
    s.emit({ phase: "done", sessionId: "s1" });
    view.unmount();
    expect(s.fail).not.toHaveBeenCalled();
  });
});
