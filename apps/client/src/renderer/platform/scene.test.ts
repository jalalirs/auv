import { describe, expect, it } from "vitest";

import { flat, pivotOf, transformed, treeOf, withColonies } from "./scene.js";
import type { WorldDocument } from "./world.js";

const world = (): WorldDocument => ({
  iocean: "world/1", name: "Tank", frame: { units: "m", axes: "x east, y north, z up", extentM: [10, 10], origin: "middle" },
  georef: null,
  layers: [{ id: "reef", kind: "reef", items: [] }, { id: "structures", kind: "structures", items: [{ id: "t1", kind: "transponder", x: 1, y: 2 }] },
           { id: "life", kind: "life", params: { count: { platax_teira: 24 } } }],
});

describe("a world as a scene", () => {
  it("makes each built colony an item of the reef, once", () => {
    const doc = withColonies(world(), [{ kind: "table", sizeM: 0.5, at: [1, 2], prim: "Tank/Coral0" }, { kind: "table", sizeM: 0.4, at: [0, 0] }]);
    const reef = doc.layers.find((l) => l.kind === "reef")!.items!;
    expect(reef.map((t) => [t.id, t.kind, t.form, t.name])).toEqual([["coral-1", "coral", "table", "Table coral 1"], ["coral-2", "coral", "table", "Table coral 2"]]);
    expect(reef[0]!.prim).toBe("Tank/Coral0");
    expect(withColonies(doc, [{ kind: "fan", sizeM: 1, at: [0, 0] }])).toBe(doc);
  });

  it("lists every coral, every thing and every species in the tree", () => {
    const doc = withColonies(world(), [{ kind: "table", sizeM: 0.5, at: [1, 2] }, { kind: "fan", sizeM: 0.4, at: [0, 0] }]);
    const ids = flat(treeOf(doc, { missions: [] })).map((n) => n.id);
    expect(ids).toEqual(expect.arrayContaining(["coral-1", "coral-2", "t1", "@life:platax_teira", "@reef:table", "@reef:fan", "@water"]));
  });

  it("turns a selection about its middle, clockwise from north", () => {
    const a = { id: "a", kind: "coral", x: 0, y: 1, headingDeg: 350 };
    const b = { id: "b", kind: "coral", x: 0, y: -1, headingDeg: 0 };
    const pivot = pivotOf([a, b])!;
    expect(pivot).toEqual({ x: 0, y: 0 });
    const turned = transformed(a, { dx: 0, dy: 0, turnDeg: 90, scale: 1 }, pivot);
    expect([turned.x, turned.y, turned.headingDeg]).toEqual([1, 0, 80]);
    expect(transformed(b, { dx: 2, dy: 0, turnDeg: 0, scale: 2 }, pivot)).toMatchObject({ x: 2, y: -1 });
  });
});
