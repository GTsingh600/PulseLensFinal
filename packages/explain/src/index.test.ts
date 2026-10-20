import { describe, expect, it } from "vitest";
import { explain } from "./index";

describe("explain", () => {
  it("returns undefined for an unknown key", () => {
    expect(explain("no.such.key")).toBeUndefined();
  });
});
