// Against a real platform, only when asked: IOCEAN_LIVE_API and IOCEAN_LIVE_TOKEN.
// A 40 MB file goes up in two parts through the API, is confirmed, and let go of.
import { describe, expect, it } from "vitest";
import { Platform } from "./index.js";

const api = process.env.IOCEAN_LIVE_API, token = process.env.IOCEAN_LIVE_TOKEN;

describe.skipIf(!api || !token)("uploading to a live platform", () => {
  it("sends a file larger than a part in parts and the platform accepts its digest", async () => {
    const platform = new Platform(api!, token);
    const org = (await platform.institution())!.id;
    const bytes = new Uint8Array(40 << 20);
    for (let i = 0; i < bytes.length; i += 65536) crypto.getRandomValues(bytes.subarray(i, i + 65536));
    const stages = new Set<string>();
    const stored = await platform.upload(org, new Blob([bytes]), {
      bucket: "ephemeral", onProgress: (stage) => stages.add(stage) });
    expect(stored.sizeBytes).toBe(40 << 20);
    expect([...stages]).toEqual(["hashing", "sending"]);
    const released = await fetch(`${api}/api/v1/organisations/${org}/objects/${stored.id}`,
      { method: "DELETE", headers: { authorization: `Bearer ${token}` } });
    expect((await released.json()).collected).toBe(true);
  }, 300_000);
});
