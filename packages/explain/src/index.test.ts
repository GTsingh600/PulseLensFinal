import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { explainers } from "./explainers.gen";
import { explain, explainMaybe } from "./index";
import { parseExplainers } from "./parse";

const md = readFileSync(new URL("../../../docs/EXPLAINERS.md", import.meta.url), "utf8");

describe("explain", () => {
  it("is built from the current EXPLAINERS.md (run `make explainers` if this fails)", () => {
    expect(explainers).toEqual(parseExplainers(md));
  });

  it("returns the exact text for a key", () => {
    expect(explain("stage.camera").title).toBe("1. Camera check");
    expect(explain("prompt.light").text).toBe("Keep looking at the screen. It will change colour a few times.");
  });

  it("returns undefined for an unknown runtime key", () => {
    expect(explainMaybe("no.such.key")).toBeUndefined();
    expect(explainMaybe("outcome.HOLD")?.text).toMatch(/^Two different families failed/);
  });
});

describe("parseExplainers", () => {
  it("reads headings and fields, and ends an entry at a ## section", () => {
    const parsed = parseExplainers("### a.b\n- title: T\n- text: X\n\n## Next\n- text: ignored\n### c\n- what: W\n");
    expect(parsed).toEqual({ "a.b": { title: "T", text: "X" }, c: { what: "W" } });
  });

  it("rejects unknown fields and duplicate keys", () => {
    expect(() => parseExplainers("### a\n- colour: red\n")).toThrow(/unknown field/);
    expect(() => parseExplainers("### a\n- text: x\n### a\n- text: y\n")).toThrow(/duplicate/);
  });
});
