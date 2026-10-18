import { describe, expect, it } from "vitest";

import { fromHash, toHash } from "./router.js";

describe("an address", () => {
  it("round-trips a page and what it is of", () => {
    const where = { page: "replay", dive: "dive_01", run: "run 2&3" };
    expect(fromHash(toHash(where))).toEqual(where);
  });
  it("leaves out what is not set", () => {
    expect(toHash({ page: "runs", by: undefined, view: "" })).toBe("#/runs");
  });
  it("is nothing when it is not one of ours", () => {
    expect(fromHash("#about")).toBeUndefined();
    expect(fromHash("")).toBeUndefined();
  });
});
