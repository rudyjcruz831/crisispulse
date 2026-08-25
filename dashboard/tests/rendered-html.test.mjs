import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

const projectRoot = new URL("../", import.meta.url);

async function render(pathname = "/", requestHeaders = {}) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${pathname}`, {
      headers: { accept: "text/html", ...requestHeaders },
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
  assert.match(html, /<html[^>]*lang="en"/i);
  assert.match(html, />Language</i);
  assert.match(html, /<option[^>]*value="en"[^>]*selected/i);
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
  assert.match(html, /48-hour reliability check/);
  assert.match(html, /Checking readiness/);
  assert.match(html, /Progress unavailable/);
  assert.match(html, /Open clocks and model benchmark/);
  assert.match(html, /Review real examples—even when there are no alerts/);
  assert.match(html, /Separate the event from the risk/);
  assert.match(html, /Training-label breakdown/);
  assert.match(html, /Flooding reported/);
  assert.match(html, /Flood risk \/ warning/);
  assert.match(html, /Heavy rain only/);
  assert.match(html, /Not flood-related/);
  assert.match(html, /Cannot determine/);
  assert.match(html, /reported flooding takes precedence over risk or warning/i);
  assert.match(html, /Safe by design/);
  assert.match(html, /U\.S\. Eastern Time/);
});

test("server-renders the saved Spanish language without an English first paint", async () => {
  const headers = { cookie: "crisispulse-language=es" };
  const [dashboardResponse, adminResponse] = await Promise.all([
    render("/", headers),
    render("/admin", headers),
  ]);
  assert.equal(dashboardResponse.status, 200);
  assert.equal(adminResponse.status, 200);

  const [dashboardHTML, adminHTML] = await Promise.all([
    dashboardResponse.text(),
    adminResponse.text(),
  ]);
  for (const html of [dashboardHTML, adminHTML]) {
    assert.match(html, /<html[^>]*lang="es"/i);
    assert.match(html, />Idioma</i);
    assert.match(html, /<option[^>]*value="es"[^>]*selected/i);
  }

  assert.match(dashboardHTML, /<title>CrisisPulse — Señales de reportes de inundaciones<\/title>/i);
  assert.match(dashboardHTML, /Monitor global de reportes de inundaciones/i);
  assert.doesNotMatch(dashboardHTML, /Global flood reporting monitor/i);
  assert.match(adminHTML, /<title>Administración de CrisisPulse — Consola de operaciones<\/title>/i);
  assert.match(adminHTML, /Inundación reportada/);
  assert.match(adminHTML, /Riesgo o alerta de inundación/);
  assert.match(adminHTML, /Solo lluvia intensa/);
  assert.match(adminHTML, /No relacionado con inundaciones/);
  assert.match(adminHTML, /No se puede determinar/);
  assert.doesNotMatch(adminHTML, /Know what is working before customers do/i);
});

test("removes the disposable starter preview", async () => {
  const [page, adminPage, globalStyles, layout, i18n, i18nServer, i18nShared, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/admin/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/i18n.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/i18n-server.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/i18n-shared.ts", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.deepEqual(await readdir(new URL("app/_sites-preview", projectRoot)), []);
  assert.doesNotMatch(page, /codex-preview|SkeletonPreview/);
  assert.match(page, /Real event/);
  assert.match(page, /Irrelevant news/);
  assert.match(page, /Uncertain/);
  const mainReviewOptions = page.match(/const reviewOptions:[\s\S]*?= \[([\s\S]*?)\n\s*\];/)?.[1];
  assert.ok(mainReviewOptions, "main dashboard review options should be present");
  assert.deepEqual(
    [...mainReviewOptions.matchAll(/value:\s*"([^"]+)"/g)].map((match) => match[1]),
    ["confirmed_event", "irrelevant_news", "uncertain"],
    "main dashboard signal review must remain a separate three-way taxonomy",
  );
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
  assert.match(adminPage, /storyUnit:\s*t\(prediction\.stories_at_detection === 1 \? "story" : "stories"\)/);
  assert.match(adminPage, /domainUnit:\s*t\(prediction\.domains_at_detection === 1 \? "domain" : "domains"\)/);
  assert.match(adminPage, /adminStatusAvailability/);
  assert.match(adminPage, /setAdminStatus\(null\)/);
  assert.match(adminPage, /Never retain a previous Go result/);
  assert.match(adminPage, /Fail closed while checking/);
  assert.match(adminPage, /fetchJSONWithTimeout/);
  assert.match(adminPage, /5_000/);
  assert.match(adminPage, /refreshEvidenceBlocked/);
  assert.match(adminPage, /latest collection needs attention/);
  assert.match(adminPage, /hasExplicitTimezone/);
  assert.match(adminPage, /\[\+-\]\\d\{2\}:\\d\{2\}/);
  assert.match(adminPage, /ready_for_pilot_setup/);
  assert.match(adminPage, /coverage_percent/);
  assert.match(adminPage, /15-minute intervals covered/);
  assert.match(adminPage, /failed_runs/);
  assert.match(adminPage, /missed_runs/);
  assert.match(adminPage, /interrupted_runs/);
  assert.match(adminPage, /current_stale/);
  assert.match(adminPage, /backup_verified/);
  assert.match(adminPage, /Go: ready for private pilot setup/);
  assert.match(adminPage, /Check restarted/);
  assert.match(adminPage, /Keep observing/);
  assert.match(adminPage, /<progress/);
  assert.match(adminPage, /aria-live="polite"/);
  assert.match(adminPage, /<time dateTime=/);
  assert.match(adminPage, /time while the PC is off does not count/);
  assert.match(adminPage, /It does not publish the site or grant public access/);
  assert.doesNotMatch(adminPage, /customer-ready/i);
  assert.match(adminPage, /\/api\/v1\/quality\/articles\/summary/);
  assert.match(adminPage, /Flooding reported/);
  assert.match(adminPage, /Flood risk \/ warning/);
  assert.match(adminPage, /Heavy rain only/);
  assert.match(adminPage, /Not flood-related/);
  assert.match(adminPage, /Cannot determine/);
  assert.match(adminPage, /Inundación reportada/);
  assert.match(adminPage, /Riesgo o alerta de inundación/);
  assert.match(adminPage, /Solo lluvia intensa/);
  assert.match(adminPage, /No relacionado con inundaciones/);
  assert.match(adminPage, /No se puede determinar/);
  assert.match(adminPage, /Optional context tags/);
  assert.match(adminPage, /<details className="article-context-tags">/);
  assert.match(adminPage, /<summary>/);
  assert.match(adminPage, /Etiquetas de contexto opcionales/);
  assert.match(adminPage, /do not replace the primary label or control alerts/);
  assert.match(adminPage, /no sustituyen la etiqueta principal ni controlan las alertas/);
  assert.match(adminPage, /lowercase words joined by hyphens, up to 32 characters each/);
  assert.match(adminPage, /palabras en minúsculas unidas por guiones, con un máximo de 32 caracteres/);
  assert.match(adminPage, /select its highlighted primary label again to save a correction/);
  assert.match(adminPage, /seleccione de nuevo su etiqueta principal resaltada para guardar una corrección/);
  const contextTagSuggestions = adminPage.match(/const articleContextTagSuggestions:[\s\S]*?= \[([\s\S]*?)\n\];/)?.[1];
  assert.ok(contextTagSuggestions, "article context-tag suggestions should be present");
  assert.deepEqual(
    [...contextTagSuggestions.matchAll(/value:\s*"([^"]+)"/g)].map((match) => match[1]),
    ["fatality", "heavy-rain", "flood-damage", "evacuation", "rescue", "cleanup", "infrastructure", "storm-impact"],
    "suggested article context tags must keep stable stored slugs",
  );
  assert.match(adminPage, /const maxArticleContextTags = 8/);
  assert.match(adminPage, /const maxArticleContextTagLength = 32/);
  assert.match(adminPage, /replace\(\/\[\^\\p\{L\}\\p\{N\}\]\+\/gu, "-"\)/);
  assert.match(adminPage, /aria-pressed=\{selected\}/);
  assert.match(adminPage, /htmlFor=\{tagInputID\}/);
  assert.match(adminPage, /onSubmit=\{\(event\) =>/);
  assert.match(adminPage, /removeArticleTag\(article, tag\)/);
  assert.match(adminPage, /body: JSON\.stringify\(\{ article_id: article\.article_id, decision, tags \}\)/);
  assert.match(adminPage, /const savedTags = normalizeArticleContextTags\(payload\.review\.tags\)/);
  assert.match(adminPage, /decision_schema_version/);
  assert.match(adminPage, /reported_flooding_articles/);
  assert.match(adminPage, /flood_risk_warning_articles/);
  assert.match(adminPage, /heavy_rain_only_articles/);
  assert.match(adminPage, /not_flood_related_articles/);
  assert.match(adminPage, /legacy_reviews/);
  assert.match(adminPage, /high_match_flood_related_rate/);
  assert.match(adminPage, /weak_match_flood_related_rate/);
  assert.match(adminPage, /Publisher-provided title/);
  assert.match(adminPage, /Manually verified publisher title/);
  assert.match(adminPage, /Cleaned from publisher URL/);
  assert.match(adminPage, /No trustworthy title available/);
  assert.match(adminPage, /balanced daily sample/i);
  assert.match(adminPage, /articleUnit:\s*t\(qualitySample\.articles\.length === 1 \? "article" : "articles"\)/);
  assert.match(adminPage, /recordUnit:\s*t\(qualitySample\.archive_articles === 1 \? "record" : "records"\)/);
  assert.match(adminPage, /America\/New_York/);
  assert.match(adminPage, /Raw archive usage/);
  assert.match(adminPage, /raw_storage_limit_bytes/);
  assert.match(adminPage, /Permanent article archive/);
  assert.match(adminPage, /article_archive_bytes/);
  assert.match(adminPage, /title_backfill_updated_articles/);
  assert.match(adminPage, /titles added last run/);
  assert.match(adminPage, /filter\(\(article\) => !hasDetailedArticleReview\(article\)\)/);
  assert.match(adminPage, /Legacy label — re-label required/);
  assert.match(adminPage, /Training-label counts are temporarily unavailable/);
  assert.match(adminPage, /qualitySummary === null \? "—"/);
  assert.match(adminPage, /hasLegacyArticleReview/);
  assert.match(adminPage, /aria-describedby=\{`article-label-definition-\$\{option\.value\}`\}/);
  assert.match(adminPage, /aria-pressed=\{activeDecision === option\.value\}/);
  assert.match(adminPage, /review-selected-check/);
  assert.match(adminPage, /Show reviewed/);
  assert.match(adminPage, /Saving this answer/);
  assert.match(adminPage, /Answer saved/);
  assert.match(adminPage, /The card was removed from Needs review/);
  assert.match(adminPage, /focusAfterReview/);
  assert.match(adminPage, /qualityNoticeRef/);
  assert.match(adminPage, /nextReviewButton/);
  assert.match(adminPage, /tabIndex=\{-1\}/);
  assert.match(adminPage, /const qualitySampleReady = qualitySummary\?\.status === "sample_ready"/);
  assert.match(adminPage, /Balanced strong and blocked minimum reached/);
  assert.match(adminPage, /Total minimum reached; strong and blocked labels still need balance/);
  assert.doesNotMatch(adminPage, /resolvedReviews >= minimumReviews/);
  assert.match(adminPage, /Today’s review queue has no pending cards/);
  assert.match(globalStyles, /\.quality-review-notice\.success/);
  assert.match(globalStyles, /\.quality-review-notice\.error/);
  assert.match(globalStyles, /\.review-button\.selected:disabled/);
  assert.match(globalStyles, /\.article-quality-card \.review-actions \{ grid-template-columns: repeat\(2/);
  assert.match(globalStyles, /\.article-quality-card \.review-button\.cannot-determine[^}]*grid-column: 1 \/ -1/);
  assert.match(globalStyles, /\.article-quality-card \.review-button[^}]*min-height: 48px/);
  assert.match(globalStyles, /\.article-tag-suggestions button[^}]*min-height: 54px/);
  assert.match(globalStyles, /\.article-context-tags summary[^}]*min-height: 44px/);
  assert.match(globalStyles, /\.article-context-tags summary:focus-visible[^}]*outline: 3px solid var\(--amber\)/);
  assert.match(globalStyles, /\.selected-article-tags button[^}]*min-height: 44px[^}]*min-width: 44px/);
  assert.match(globalStyles, /\.article-custom-tag-form input, \.article-custom-tag-form button[^}]*min-height: 44px/);
  assert.match(globalStyles, /\.article-tag-suggestions button:focus-visible[^}]*outline: 3px solid var\(--amber\)/);
  assert.match(globalStyles, /@media \(max-width: 680px\)[\s\S]*?\.article-quality-card \.review-actions \{ grid-template-columns: 1fr; \}/);
  assert.match(globalStyles, /@media \(max-width: 680px\)[\s\S]*?\.article-tag-suggestions \{ grid-template-columns: 1fr; \}/);
  assert.match(globalStyles, /\.readiness-progress progress/);
  assert.match(globalStyles, /\.readiness-metrics/);
  assert.match(globalStyles, /\.readiness-blockers/);
  assert.match(globalStyles, /\.readiness-decision\.restarted/);
  assert.doesNotMatch(page, /127\.0\.0\.1:8080/);
  assert.match(layout, /CrisisPulse — Flood reporting signals/);
  assert.match(layout, /getRequestLocale/);
  assert.match(i18n, /LanguageSwitcher/);
  assert.match(i18nShared, /crisispulse-language/);
  assert.match(i18n, /localStorage\.setItem/);
  assert.match(i18n, /document\.documentElement\.lang/);
  assert.match(i18nServer, /cookies\(\)/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
});
