import { createHash, randomBytes } from "node:crypto";
import { describe, expect, it } from "vitest";
import { Sha256 } from "./sha256.js";

describe("Sha256", () => {
  it("agrees with node's on the empty input, a short one and one fed in odd pieces", () => {
    expect(new Sha256().hex()).toBe(createHash("sha256").digest("hex"));
    expect(new Sha256().update(new TextEncoder().encode("abc")).hex())
      .toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    const bytes = randomBytes(1_000_003);
    const hash = new Sha256();
    for (let at = 0; at < bytes.length; at += 4097) hash.update(bytes.subarray(at, at + 4097));
    expect(hash.hex()).toBe(createHash("sha256").update(bytes).digest("hex"));
  });
});
