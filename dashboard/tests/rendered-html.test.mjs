import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

const projectRoot = new URL("../", import.meta.url);

async function render(pathname = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${pathname}`, {
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
  const dashboardData = JSON.parse(
    await readFile(new URL("../data/dashboard.json", import.meta.url), "utf8"),
  );
  assert.match(html, /<title>CrisisPulse — Flood reporting signals<\/title>/i);
  assert.match(html, /unusual reporting signals? need(?:s)? review|No unusual reporting signals right now/i);
  assert.match(html, new RegExp(dashboardData.snapshot.clean_articles.toLocaleString("en-US")));
  assert.match(html, /Signals with enough evidence/);
  assert.match(html, /Latest flood coverage/);
  assert.match(html, /evidence, not automatic confirmation of a physical incident/i);
  assert.match(html, /Review queue/);
  assert.match(html, /Will reporting spread in the next six hours/);
  assert.match(html, /First chronological (model|benchmark pending)/);
  assert.match(html, /Evidence review required|System behaving as designed/);
  if (dashboardData.snapshot.candidates > 0) {
    assert.match(html, /Needs review/);
  } else {
    assert.match(html, /No candidate signals are waiting for review/);
  }
  assert.match(html, new RegExp(dashboardData.forecast.eligible_windows.toLocaleString("en-US")));
  if (dashboardData.forecast.model.status === "ready") {
    const averagePrecision = `${(dashboardData.forecast.model.test_metrics.average_precision * 100).toFixed(1)}%`;
    assert.match(html, new RegExp(averagePrecision.replace(".", "\\.")));
  }
  assert.match(html, /Candidate anomalies/);
  assert.match(html, /Verified local snapshot/);
  assert.match(html, /not an emergency warning system/i);
  assert.doesNotMatch(html, /codex-preview|SkeletonPreview|react-loading-skeleton/i);
});

test("server-renders the admin operations and quality page", async () => {
  const response = await render("/admin");
  assert.equal(response.status, 200);
  const html = await response.text();

  assert.match(html, /<title>CrisisPulse Admin — Operations console<\/title>/i);
  assert.match(html, /Know what is working before customers do/);
  assert.match(html, /Paid pilot readiness/);
  assert.match(html, /Open clocks and model benchmark/);
  assert.match(html, /Review real examples—even when there are no alerts/);
  assert.match(html, /Judge physical flooding/);
  assert.match(html, /Safe by design/);
  assert.match(html, /U\.S\. Eastern Time/);
});

test("removes the disposable starter preview", async () => {
  const [page, adminPage, globalStyles, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.deepEqual(await readdir(new URL("app/_sites-preview", projectRoot)), []);
  assert.doesNotMatch(page, /codex-preview|SkeletonPreview/);
  assert.match(page, /Real event/);
  assert.match(page, /Irrelevant news/);
  assert.match(page, /Uncertain/);
  assert.match(page, /Direct publisher evidence/);
  assert.match(page, /Multi-source coverage/);
  assert.match(page, /Read publisher report/);
  assert.match(page, /csc: "CSC"/);
  assert.match(page, /ust: "UST"/);
  assert.match(page, /preserveHeadlineAcronyms/);
  assert.match(page, /Compare publisher versions/);
  assert.match(page, /Clear conflicts with a URL-derived headline are downgraded/);
  assert.match(page, /GDELT tag:/);
  assert.match(page, /Measure before you market/);
  assert.match(page, /Download labels \(\.csv\)/);
  assert.match(page, /\/api\/v1\/reviews\/summary/);
  assert.match(page, /\/api\/v1\/reviews\/export\.csv/);
  assert.match(page, /Forecast lab/i);
  assert.match(page, /Future data stays hidden until maturity/);
  assert.match(page, /First chronological model/);
  assert.match(page, /Measured on later holdout hours/);
  assert.match(page, /Ranking score—not a calibrated probability/);
  assert.match(page, /false_alerts_per_day/);
  assert.match(page, /evaluation_ready_windows/);
  assert.match(page, /const snapshotURL = "\/api\/v1\/snapshot"/);
  assert.match(page, /const reviewsURL = "\/api\/v1\/reviews"/);
  assert.match(page, /href="\/admin"/);
  assert.match(adminPage, /\/api\/v1\/admin\/status/);
  assert.match(adminPage, /\/api\/v1\/quality\/articles\/summary/);
  assert.match(adminPage, /Relevant flood/);
  assert.match(adminPage, /Not relevant/);
  assert.match(adminPage, /Publisher-provided title/);
  assert.match(adminPage, /Manually verified publisher title/);
  assert.match(adminPage, /Cleaned from publisher URL/);
  assert.match(adminPage, /No trustworthy title available/);
  assert.match(adminPage, /balanced daily sample/i);
  assert.match(adminPage, /America\/New_York/);
  assert.match(adminPage, /Raw archive usage/);
  assert.match(adminPage, /raw_storage_limit_bytes/);
  assert.match(adminPage, /Permanent article archive/);
  assert.match(adminPage, /article_archive_bytes/);
  assert.match(adminPage, /title_backfill_updated_articles/);
  assert.match(adminPage, /titles added last run/);
  assert.match(adminPage, /filter\(\(article\) => !article\.decision\)/);
  assert.match(adminPage, /Show reviewed/);
  assert.match(adminPage, /Saving this answer/);
  assert.match(adminPage, /Answer saved/);
  assert.match(adminPage, /The card was removed from Needs review/);
  assert.match(adminPage, /const qualitySampleReady = qualitySummary\?\.status === "sample_ready"/);
  assert.match(adminPage, /qualitySampleReady \? "Balanced minimum reached"/);
  assert.match(adminPage, /Total minimum reached; strong and blocked labels still need balance/);
  assert.doesNotMatch(adminPage, /resolvedReviews >= minimumReviews/);
  assert.match(adminPage, /Today’s review queue has no pending cards/);
  assert.match(globalStyles, /\.quality-review-notice\.success/);
  assert.match(globalStyles, /\.quality-review-notice\.error/);
  assert.match(globalStyles, /\.review-button\.selected:disabled/);
  assert.doesNotMatch(page, /127\.0\.0\.1:8080/);
  assert.match(layout, /CrisisPulse — Flood reporting signals/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
});
