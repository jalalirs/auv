import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { startedThisMonth } from "../screens/Organisation.js";
import { chooseOrganisation, rememberOrganisation, type Held } from "./held.js";

const own = { id: "org_own", slug: "ali-x", name: "Ali", personalOf: "prin_ali", createdAt: "" };
const kaust = { id: "org_kaust", slug: "kaust", name: "KAUST", createdAt: "" };

describe("which organisation the application works in", () => {
  // The tests run outside a browser; a map stands in for its storage.
  beforeAll(() => {
    const kept = new Map<string, string>();
    globalThis.localStorage = {
      getItem: (k: string) => kept.get(k) ?? null,
      setItem: (k: string, v: string) => void kept.set(k, v),
      removeItem: (k: string) => void kept.delete(k),
      clear: () => kept.clear(),
      key: () => null,
      get length() { return kept.size; },
    };
  });
  afterEach(() => localStorage.clear());

  it("prefers an institution to the person's own space", () => {
    expect(chooseOrganisation([own, kaust])?.id).toBe("org_kaust");
  });

  it("keeps the one chosen, while the person still belongs to it", () => {
    rememberOrganisation("org_own");
    expect(chooseOrganisation([own, kaust])?.id).toBe("org_own");
    expect(chooseOrganisation([kaust])?.id).toBe("org_kaust");
  });

  it("is the person's own space when that is all there is", () => {
    expect(chooseOrganisation([own])?.id).toBe("org_own");
    expect(chooseOrganisation([])).toBeUndefined();
  });
});

describe("dives this month", () => {
  it("counts runs asked for since the first of the month, UTC", () => {
    const run = (requestedAt: string) => ({ run: { requestedAt } }) as unknown as Held["runs"][number];
    const held = { runs: [run("2026-10-31T23:00:00Z"), run("2026-10-01T00:00:00Z"), run("2026-09-30T23:59:59Z")] } as Held;
    expect(startedThisMonth(held, new Date("2026-10-31T12:00:00Z"))).toBe(2);
  });
});
