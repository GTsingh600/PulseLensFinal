import { describe, expect, it } from "vitest";
import { eventTypeValues, familyValues, routeValues, type CheckResult } from "./index";

describe("@pulselens/types", () => {
  it("mirrors the SPEC 5 event types", () => {
    expect(eventTypeValues).toHaveLength(19);
    expect(eventTypeValues[0]).toBe("session.created");
    expect(eventTypeValues).toContain("decision");
  });

  it("mirrors families and routes", () => {
    expect(familyValues).toContain("continuity");
    expect(routeValues).toEqual(["PASS", "ADD_CHECKS", "AGENT_CHALLENGE", "ASSISTED_KYC", "HOLD"]);
  });

  it("types a CheckResult like the server sends it", () => {
    const r: CheckResult = {
      check_id: "optical.face_neck", unit: "light", family: "optical", status: "abstain",
      score: null, threshold: null, threshold_source: null, band: null, quality: 0.2, features: {},
      reason: "The neck was out of frame on 9 of 10 pulses.", explainer: "check.optical.face_neck",
      plot: null, evidence_frames: [],
    };
    expect(r.status).toBe("abstain");
  });
});
