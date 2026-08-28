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

test("the Coral City blueprint opens on the standalone architecture", async () => {
  const response = await worker.fetch(
    new Request("https://coral-city.test/"),
    { ASSETS: assets },
    context,
  );
  const html = await response.text();

  assert.equal(response.status, 200);
  assert.match(html, /Coral City/);
  assert.match(html, /How Coral City fits together\./);
  assert.match(html, /Standalone Coral City architecture/);
  assert.match(html, /Coral City control plane/);
  assert.match(html, /Applications/);
  assert.match(html, /Scientific data plane/);
  assert.match(html, /Compute plane/);
  assert.match(html, /Field plane/);
  assert.match(html, />Product</);
  assert.match(html, />Releases</);
  assert.match(html, />Models</);
  assert.match(html, />Deployment</);
  assert.doesNotMatch(html, /codex-preview|SkeletonPreview/);
});
