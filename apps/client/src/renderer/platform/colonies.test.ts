import { describe, expect, it } from "vitest";

import { asEdits, colonyItem, Near, readColonies, rowOf, untouched, writeColonies } from "./colonies.js";

const made = () => writeColonies({
  version: "ver_1", digest: "d", forms: ["massive", "branching"],
  x: new Float32Array([0, 10, 10.5]), y: new Float32Array([0, 0, 0.5]),
  sizeM: new Float32Array([0.5, 1, 0.25]), builtDeg: new Float32Array([0, 90, 180]), form: new Uint8Array([0, 1, 1]),
});

describe("a big reef's colonies file", () => {
  it("reads back what was written, row by row", () => {
    const p = readColonies(made());
    expect(p.count).toBe(3);
    expect(p.version).toBe("ver_1");
    expect(p.forms[p.form[1]!]).toBe("branching");
    expect([...p.sizeM]).toEqual([0.5, 1, 0.25]);
    expect(p.builtDeg[2]).toBe(180);
  });
  it("names row i coral-<i+1>, and nothing else is a row", () => {
    expect(rowOf("coral-1", 3)).toBe(0);
    expect(rowOf("coral-4", 3)).toBeUndefined();
    expect(rowOf("coral-new-01ABC", 3)).toBeUndefined();
  });
  it("finds the colony nearest a click", () => {
    const near = new Near(readColonies(made()), 5);
    expect(near.nearest(10.4, 0.4, 1)).toBe(2);
    expect(near.within(0, 0, 11).sort()).toEqual([0, 1, 2]);
    expect(near.nearest(50, 50, 1)).toBeUndefined();
  });
  it("refuses a file that is not one", () => {
    expect(() => readColonies(new ArrayBuffer(16))).toThrow();
  });
});

describe("a big reef's edits", () => {
  const p = readColonies(made());
  const doc = (items: object[]) => ({ describedBy: "iocean/world/1", layers: [{ id: "reef", kind: "reef", items }] }) as never;
  it("keeps only the colonies somebody changed, over the build they were changed on", () => {
    const left = colonyItem(p, 0, "Massive coral 1");
    const moved = { ...colonyItem(p, 1, "Branching coral 1"), x: 12 };
    const hidden = { ...colonyItem(p, 2, "Branching coral 2"), hidden: true };
    const out = asEdits(doc([left, moved, hidden, { id: "coral-new-a", kind: "coral", form: "massive", x: 1, y: 1 }]), p);
    const reef = (out as { layers: { params: Record<string, unknown>; items: { id: string }[] }[] }).layers[0]!;
    expect(reef.items.map((t) => t.id)).toEqual(["coral-2", "coral-3", "coral-new-a"]);
    expect(reef.params).toMatchObject({ colonyEdits: true, editedOn: "ver_1" });
    expect(untouched(left, p)).toBe(true);
  });
});
