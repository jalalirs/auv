import assert from "node:assert/strict";
import test from "node:test";

import worker from "../dist/server/index.js";

const assets = {
  fetch: async () => new Response("Not found", { status: 404 }),
};

const context = {
  waitUntil() {},
  passThroughOnException() {},
};

test("the Coral City blueprint renders its canonical program sections", async () => {
  const response = await worker.fetch(
    new Request("https://coral-city.test/"),
    { ASSETS: assets },
    context,
  );
  const html = await response.text();

  assert.equal(response.status, 200);
  assert.match(html, /Coral City/);
  assert.match(html, /A living Red Sea\./);
  assert.match(html, /Before we enter it\./);
  assert.match(html, /One system, not disconnected demos\./);
  assert.match(html, /One stable core\. Many replaceable engines\./);
  assert.match(html, /OpenDrift/);
  assert.match(html, /Environment Package/);
  assert.match(html, /Five planes\. One Coral City\./);
  assert.match(html, /Coral City control plane/);
  assert.match(html, /No ARC service or project dependency is implied\./);
  assert.match(html, /Every phase ends in a working system\./);
  assert.match(html, /R1 · Scientific Reef Atlas/);
  assert.match(html, /ACCEPTANCE TESTS/);
  assert.doesNotMatch(html, /codex-preview|SkeletonPreview/);
});
