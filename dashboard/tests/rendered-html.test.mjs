import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

const projectRoot = new URL("../", import.meta.url);

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the CrisisPulse evidence dashboard", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>CrisisPulse — Flood reporting signals<\/title>/i);
  assert.match(html, /No unusual reporting signals right now\./);
  assert.match(html, /13,196/);
  assert.match(html, /Signals with enough evidence/);
  assert.match(html, /Review queue/);
  assert.match(html, /No candidate signals are waiting for review/);
  assert.match(html, /2 normal/i);
  assert.match(html, /Candidate anomalies/);
  assert.match(html, /Verified local snapshot/);
  assert.match(html, /not an emergency warning system/i);
  assert.doesNotMatch(html, /codex-preview|SkeletonPreview|react-loading-skeleton/i);
});

test("removes the disposable starter preview", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.deepEqual(await readdir(new URL("app/_sites-preview", projectRoot)), []);
  assert.doesNotMatch(page, /codex-preview|SkeletonPreview/);
  assert.match(page, /Real event/);
  assert.match(page, /Irrelevant news/);
  assert.match(page, /Uncertain/);
  assert.match(page, /const snapshotURL = "\/api\/v1\/snapshot"/);
  assert.match(page, /const reviewsURL = "\/api\/v1\/reviews"/);
  assert.doesNotMatch(page, /127\.0\.0\.1:8080/);
  assert.match(layout, /CrisisPulse — Flood reporting signals/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
});
