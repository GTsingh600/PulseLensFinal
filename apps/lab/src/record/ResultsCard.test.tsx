import { render, screen, waitFor, within } from "@testing-library/react";
import { explain } from "@pulselens/explain";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResultsCard, useReport, type Report } from "./ResultsCard";

const check = (id: string, family: string, status: "pass" | "fail" | "abstain", reason: string) => ({
  check_id: id, unit: "light", family, status, score: null, threshold: null, threshold_source: "bootstrap", band: null,
  quality: 1, features: {}, reason, explainer: `check.${id}`, plot: { type: "echo", ref: id }, evidence_frames: [],
});

// The shape of the D01 session ba483afb7431247b's report, trimmed.
const DONE: Report = {
  status: "done",
  provisional_thresholds: true,
  qc: { fps: 10.4, frames: 221, dropped: 0, acks_ok: 10, pulses: 10, clock_source: "captureTime", browser: "Brave 155", face_visible: 1, neck_visible: 0.82 },
  checks: [
    check("camera.fingerprint", "camera", "pass", "The sensor pattern in odd frames matches the even frames (PCE 556, limit 200)."),
    check("optical.light.delay", "optical", "abstain", "The camera delivered 10.4 fps, below the 12 fps needed to time the echo."),
    check("optical.face_neck", "optical", "fail", "The face lagged the neck by 96 ms on 6 of 6 flashes."),
  ] as never,
};

afterEach(() => vi.unstubAllGlobals());

describe("ResultsCard", () => {
  it("says it is analysing while the report runs", () => {
    render(<ResultsCard report={{ status: "running" }} />);
    expect(screen.getByRole("region", { name: "Results" }).getAttribute("aria-busy")).toBe("true");
  });

  it("shows the QC numbers, a count per status and every check under its family with its reason", () => {
    render(<ResultsCard report={DONE} />);
    expect(screen.getByText("1 pass")).toBeTruthy();
    expect(screen.getByText("1 fail")).toBeTruthy();
    expect(screen.getByText("1 not judged")).toBeTruthy();
    const qc = screen.getByLabelText("Recording quality");
    expect(qc.textContent).toContain("10.4 fps");
    expect(qc.textContent).toContain("82%");
    expect(qc.textContent).toContain("10 of 10");
    const optical = screen.getByRole("region", { name: explain("family.optical").title });
    const row = within(optical).getByRole("group", { name: explain("check.optical.face_neck").title });
    expect(row.textContent).toContain("Fail");
    expect(row.textContent).toContain("lagged the neck by 96 ms");
    expect(row.textContent).toContain(explain("check.optical.face_neck").why!);
    const abstained = within(optical).getByRole("group", { name: explain("check.optical.light.delay").title });
    expect(abstained.textContent).toContain(explain("status.abstain").text!);
  });

  it("carries the PROVISIONAL THRESHOLDS label while thresholds are bootstrap (CLAUDE.md rule 4)", () => {
    render(<ResultsCard report={DONE} />);
    expect(screen.getByRole("note").textContent).toContain("PROVISIONAL THRESHOLDS");
    render(<ResultsCard report={{ ...DONE, provisional_thresholds: false }} />);
    expect(screen.getAllByRole("note")).toHaveLength(1);
  });

  it("explains an analysis error instead of showing an empty card", () => {
    render(<ResultsCard report={{ status: "error", error: "FileNotFoundError: no frames.jsonl" }} />);
    expect(screen.getByRole("alert").textContent).toContain("no frames.jsonl");
  });
});

function Probe({ id }: { id: string }) {
  const r = useReport(id, "tok", 5);
  return <p data-testid="status">{r.status}</p>;
}

describe("useReport", () => {
  it("starts the analysis with the token, polls while running and stops when done", async () => {
    const replies = [{ status: "running" }, { status: "running" }, DONE];
    const fetch = vi.fn(async (url: string, init: RequestInit) => {
      expect((init.headers as Record<string, string>)["X-Session-Token"]).toBe("tok");
      return new Response(JSON.stringify(url.endsWith("/analyze") ? { status: "running" } : replies.shift()));
    });
    vi.stubGlobal("fetch", fetch);
    render(<Probe id="s1" />);
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("done"));
    const urls = fetch.mock.calls.map((c) => c[0]);
    expect(urls[0]).toBe("/api/sessions/s1/analyze");
    expect(urls.filter((u) => u.endsWith("/report"))).toHaveLength(3);
  });

  it("reports a refused request as an error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("no", { status: 401 })));
    render(<Probe id="s2" />);
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("error"));
  });
});
