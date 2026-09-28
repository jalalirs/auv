// What a line says when there is nothing on it to choose.
//
// It counted only what could be chosen, so a line holding four vehicles, none
// of which carries a hull, read "Choose… / 0 to choose from". True, and it
// tells you nothing: not that there are four, not that they are held back for
// one reason, not that the thing to fix is the package rather than the choice.
// Every vehicle on this platform is in that state, so this line is the one
// standing between somebody and a dive.

import { describe, expect, it } from "vitest";

import { summaryOf } from "./Line.js";

describe("what a line says with nothing chosen", () => {
  it("counts what can be chosen when anything can", () => {
    expect(summaryOf([{}, {}, { later: "no hull yet" }])).toBe("2 to choose from");
  });

  it("names the one reason when everything is held back for it", () => {
    const four = [1, 2, 3, 4].map(() => ({ later: "no hull yet" }));
    expect(summaryOf(four)).toBe("4 here, and all are held back: no hull yet");
  });

  it("does not say 'all are' about a single one", () => {
    expect(summaryOf([{ later: "no package yet" }]))
      .toBe("1 here, and it is held back: no package yet");
  });

  it("does not pick a reason when they differ", () => {
    expect(summaryOf([{ later: "no hull yet" }, { later: "no package yet" }]))
      .toBe("2 here, none ready yet");
  });

  it("says so when the line is genuinely empty", () => {
    expect(summaryOf([])).toBe("nothing here yet");
  });

  it("never says zero of anything", () => {
    for (const c of [[], [{ later: "x" }], [{ later: "x" }, { later: "y" }]]) {
      expect(summaryOf(c)).not.toMatch(/\b0\b/);
    }
  });
});
