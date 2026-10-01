// Why nothing answered, when it can be told.
//
// A browser reports a call it refused to make across origins exactly as it
// reports a machine that is off. This said "is the box awake?" about a box that
// was awake, which sends somebody to check the wrong thing.

import { describe, expect, it } from "vitest";

import { whyNothingAnswered } from "./SignIn.js";

describe("why nothing answered", () => {
  it("in a browser, names the cross-origin refusal and what to do instead", () => {
    const said = whyNothingAnswered("http://100.76.65.1:18080", "http://localhost:5173/");
    expect(said).toContain("will not let it call http://100.76.65.1:18080");
    expect(said).toContain("Sign in to http://localhost:5173");
    expect(said).not.toContain("awake");
  });

  it("on the same origin, really is a machine that did not answer", () => {
    const said = whyNothingAnswered("http://localhost:5173", "http://localhost:5173/");
    expect(said).toContain("awake");
  });

  it("in the desktop application, which is not a page on an origin, asks about the box", () => {
    expect(whyNothingAnswered("http://100.76.65.1:18080", "file:///app/index.html")).toContain("awake");
    expect(whyNothingAnswered("http://100.76.65.1:18080", null)).toContain("awake");
  });
});
