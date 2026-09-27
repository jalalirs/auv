// What the Autonomy page says about the record as it actually stands.
//
// Not a fixture: these are the eight rows the platform held on 27 September 2026,
// after `pursue` and `wary` each flew the quick suite over Looe Key.
import { describe, expect, it } from "vitest";

import { headToHead, saidAs } from "./flown.js";

const row = (name: string, flownBy: string, score: number) =>
  ({ name, flownBy, run: { state: "succeeded", outcome: { task: { score } } } } as never);

const RECORD = [
  row("bench · quick · pursue · dock", "pursue", 0.0),
  row("bench · quick · pursue · reach", "pursue", 0.174),
  row("bench · quick · pursue · transect", "pursue", 0.293),
  row("bench · quick · wary · dock", "wary", 0.0),
  row("bench · quick · wary · reach", "wary", 0.174),
  row("bench · quick · wary · transect", "wary", 0.293),
  row("bench · quick · station-hold · reach", "station-hold", 0.0),
  row("bench · quick · learned-hold · reach", "learned-hold", 0.0),
];

describe("what the page says about the record as it stands", () => {
  it("calls pursue and wary level, because they are, on all three", () => {
    const [said] = headToHead("pursue", ["wary", "station-hold", "learned-hold"], RECORD);
    expect(said!.against).toBe("wary");
    expect(said!.shared).toBe(3);
    expect(said!.better).toBe(0);
    expect(said!.same).toBe(3);
    expect(saidAs(said!)).toBe("the same as wary on all 3 shared tasks");
  });

  it("compares the deployed controllers only on the one task they flew", () => {
    const said = headToHead("station-hold", ["pursue", "learned-hold"], RECORD);
    expect(said.map((one) => [one.against, one.shared])).toEqual([
      ["pursue", 1], ["learned-hold", 1],
    ]);
    // And it tells losing apart from drawing, which is the whole point: it lost
    // to `pursue` on that task (0% against 17.4%) and drew with `learned-hold`,
    // which scored nothing either.
    const against = new Map(said.map((one) => [one.against, one]));
    expect(against.get("pursue")).toMatchObject({ shared: 1, better: 0, same: 0 });
    expect(against.get("learned-hold")).toMatchObject({ shared: 1, better: 0, same: 1 });
    expect(saidAs(against.get("pursue")!)).toBe("better than pursue on 0 of 1");
    expect(saidAs(against.get("learned-hold")!))
      .toBe("the same as learned-hold on all 1 shared task");
  });
});
