"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import bundledDashboardData from "../../data/dashboard.json";

type DashboardData = typeof bundledDashboardData;
type ArticleDecision = "relevant" | "not_relevant" | "uncertain";
type QualityArticle = {
  article_id: string;
  seen_at: string;
  title: string;
  title_source?: "manual_override" | "publisher_metadata" | "url_path" | "unavailable";
  url: string;
  source_domain: string;
  location_name: string;
  match_strength: "high" | "weak";
  review_bucket: "high_match" | "headline_conflict" | "ambiguous_match";
  review_reason: string;
  themes: string[];
  quality_flags: string[];
  decision?: ArticleDecision;
  reviewed_at?: string;
};
type QualitySample = {
  version: number;
  sample_date: string;
  archive_articles: number;
  eligible_articles: number;
  articles: QualityArticle[];
};
type ArticleQualitySummary = {
  total_reviews: number;
  relevant_articles: number;
  not_relevant_articles: number;
  uncertain: number;
  resolved_reviews: number;
  minimum_sample: number;
  remaining_to_sample: number;
  high_resolved: number;
  high_relevant: number;
  weak_resolved: number;
  weak_relevant: number;
  high_match_precision: number | null;
  weak_match_relevant_rate: number | null;
  status: "collecting_labels" | "sample_ready";
};
type ArticleReviewResponse = {
  review: {
    article_id: string;
    decision: ArticleDecision;
    reviewed_at: string;
  };
};
type SavingArticleReview = {
  articleID: string;
  decision: ArticleDecision;
};
type QualityNotice = {
  kind: "success" | "error";
  message: string;
};
type AdminStatus = {
  service: { name: string; status: string };
  refresh: {
    status: string;
    health: "healthy" | "degraded";
    started_at: string;
    finished_at: string;
    last_success_at: string;
    expected_next_refresh_at: string;
    age_minutes: number;
    message: string;
    processed_files: number;
    downloaded_files: number;
    already_present_files: number;
    retained_raw_files: number;
    retained_raw_bytes?: number;
    raw_storage_limit_bytes?: number;
    pruned_raw_files: number;
    archived_articles?: number;
    new_archived_articles?: number;
    article_archive_bytes?: number;
    title_backfill_attempted_articles?: number;
    title_backfill_updated_articles?: number;
    title_backfill_remaining_articles?: number;
    title_backfill_downgraded_articles?: number;
  };
};

const formatNumber = (value: number) => value.toLocaleString("en-US");
const formatBytes = (value: number | null | undefined) => {
  if (value === null || value === undefined || value < 0) return "—";
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)} GB`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} MB`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)} KB`;
  return `${value} B`;
};
const formatEastern = (value: string) => {
  const date = new Date(value.endsWith("Z") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value || "—";
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  });
};
const formatPercent = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;
const qualityArticlesURL = "/api/v1/quality/articles";
const qualitySummaryURL = "/api/v1/quality/articles/summary";
const qualityExportURL = "/api/v1/quality/articles/export.csv";
const articleReviewOptions: Array<{ value: ArticleDecision; label: string; tone: string }> = [
  { value: "relevant", label: "Relevant flood", tone: "confirmed" },
  { value: "not_relevant", label: "Not relevant", tone: "irrelevant" },
  { value: "uncertain", label: "Uncertain", tone: "uncertain" },
];
const safeArticleURL = (value: string) => {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
};
const settledJSON = async <T,>(result: PromiseSettledResult<Response>): Promise<T | null> => {
  if (result.status !== "fulfilled" || !result.value.ok) return null;
  try {
    return await result.value.json() as T;
  } catch {
    return null;
  }
};

export default function AdminPage() {
  const [dashboardData, setDashboardData] = useState<DashboardData>(bundledDashboardData);
  const [qualitySample, setQualitySample] = useState<QualitySample | null>(null);
  const [qualitySummary, setQualitySummary] = useState<ArticleQualitySummary | null>(null);
  const [adminStatus, setAdminStatus] = useState<AdminStatus | null>(null);
  const [connection, setConnection] = useState<"loading" | "ready" | "offline">("loading");
  const [checking, setChecking] = useState(false);
  const [savingArticleReview, setSavingArticleReview] = useState<SavingArticleReview | null>(null);
  const [qualityNotice, setQualityNotice] = useState<QualityNotice | null>(null);
  const [showReviewedArticles, setShowReviewedArticles] = useState(false);
  const requestInFlight = useRef(false);
  const reviewRequestInFlight = useRef(false);
  const { snapshot, forecast } = dashboardData;
  const pendingQualityArticles = qualitySample?.articles.filter((article) => !article.decision) ?? [];
  const reviewedQualityArticles = qualitySample?.articles.filter((article) => Boolean(article.decision)) ?? [];
  const visibleQualityArticles = showReviewedArticles
    ? qualitySample?.articles ?? []
    : pendingQualityArticles;

  const refreshAdmin = useCallback(async (signal?: AbortSignal) => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    setChecking(true);
    try {
      const options: RequestInit = { cache: "no-store", signal };
      const [snapshotResult, statusResult, qualityResult, qualitySummaryResult] = await Promise.allSettled([
        fetch("/api/v1/snapshot", options),
        fetch("/api/v1/admin/status", options),
        fetch(qualityArticlesURL, options),
        fetch(qualitySummaryURL, options),
      ]);
      const [nextData, nextStatus, nextQuality, nextQualitySummary] = await Promise.all([
        settledJSON<DashboardData>(snapshotResult),
        settledJSON<AdminStatus>(statusResult),
        settledJSON<QualitySample>(qualityResult),
        settledJSON<ArticleQualitySummary>(qualitySummaryResult),
      ]);
      if (signal?.aborted) return;

      let live = false;
      if (nextData?.snapshot && nextData.forecast) {
        setDashboardData(nextData);
        live = true;
      }
      if (nextStatus?.service && nextStatus.refresh) {
        setAdminStatus(nextStatus);
        live = true;
      }
      if (nextQuality?.articles) {
        setQualitySample((current) => {
          if (!current) return nextQuality;
          const locallySaved = new Map(
            current.articles
              .filter((article) => article.decision)
              .map((article) => [article.article_id, article]),
          );
          return {
            ...nextQuality,
            articles: nextQuality.articles.map((article) => {
              const saved = locallySaved.get(article.article_id);
              return saved?.decision
                ? { ...article, decision: saved.decision, reviewed_at: saved.reviewed_at }
                : article;
            }),
          };
        });
      }
      if (nextQualitySummary) setQualitySummary(nextQualitySummary);
      setConnection(live ? "ready" : "offline");
    } finally {
      requestInFlight.current = false;
      if (!signal?.aborted) setChecking(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const initialCheck = window.setTimeout(() => void refreshAdmin(controller.signal), 0);
    const interval = window.setInterval(() => void refreshAdmin(controller.signal), 60_000);
    return () => {
      controller.abort();
      window.clearTimeout(initialCheck);
      window.clearInterval(interval);
    };
  }, [refreshAdmin]);

  useEffect(() => {
    if (qualityNotice?.kind !== "success") return;
    const timeout = window.setTimeout(() => setQualityNotice(null), 6_500);
    return () => window.clearTimeout(timeout);
  }, [qualityNotice]);

  const refreshQualitySummary = async () => {
    try {
      const response = await fetch(qualitySummaryURL, { cache: "no-store" });
      if (response.ok) setQualitySummary(await response.json() as ArticleQualitySummary);
    } catch {
      // The answer is already saved; a delayed progress refresh must not report a false failure.
    }
  };

  const saveArticleReview = async (article: QualityArticle, decision: ArticleDecision) => {
    if (reviewRequestInFlight.current) return;
    reviewRequestInFlight.current = true;
    setSavingArticleReview({ articleID: article.article_id, decision });
    setQualityNotice(null);
    let sampleChanged = false;
    try {
      const response = await fetch(qualityArticlesURL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ article_id: article.article_id, decision }),
      });
      if (!response.ok) {
        sampleChanged = response.status === 400;
        throw new Error(`Article review API returned ${response.status}`);
      }
      const payload = await response.json() as ArticleReviewResponse;
      if (payload.review.article_id !== article.article_id || payload.review.decision !== decision) {
        throw new Error("Article review API returned an unexpected answer");
      }
      setQualitySample((current) => current ? {
        ...current,
        articles: current.articles.map((item) => item.article_id === article.article_id
          ? { ...item, decision: payload.review.decision, reviewed_at: payload.review.reviewed_at }
          : item),
      } : current);
      const decisionLabel = articleReviewOptions.find((option) => option.value === decision)?.label ?? decision;
      const pendingAfterSave = Math.max(0, pendingQualityArticles.length - (article.decision ? 0 : 1));
      const remainingCopy = pendingAfterSave === 0
        ? "No articles in today’s queue remain."
        : `${pendingAfterSave} ${pendingAfterSave === 1 ? "article" : "articles"} still need review.`;
      setQualityNotice({
        kind: "success",
        message: decision === "uncertain"
          ? `Saved as ${decisionLabel}. It moved to Reviewed, but uncertain answers do not count toward the 20 resolved labels. ${remainingCopy}`
          : `Saved as ${decisionLabel}. The card was removed from Needs review. ${remainingCopy}`,
      });
      void refreshQualitySummary();
    } catch {
      setQualityNotice({
        kind: "error",
        message: sampleChanged
          ? "This daily sample changed before the answer was saved. The list is refreshing; please choose again."
          : "This answer was not saved. Please try again; if it continues, select Check now to confirm the local service is connected.",
      });
    } finally {
      reviewRequestInFlight.current = false;
      setSavingArticleReview(null);
      if (sampleChanged) void refreshAdmin();
    }
  };

  const modelReady = forecast.model.status === "ready";
  const refreshHealthy = connection === "ready" && adminStatus?.refresh.health === "healthy";
  const overallStatus = refreshHealthy && modelReady ? "Operating normally" : connection === "offline" ? "Local API offline" : "Attention needed";
  const resolvedReviews = qualitySummary?.resolved_reviews ?? 0;
  const minimumReviews = qualitySummary?.minimum_sample ?? 20;
  const remainingReviews = qualitySummary?.remaining_to_sample ?? Math.max(0, minimumReviews - resolvedReviews);
  const qualitySampleReady = qualitySummary?.status === "sample_ready";
  const qualityBalancePending = !qualitySampleReady && remainingReviews === 0;
  const qualityProgress = minimumReviews > 0
    ? Math.min(100, (resolvedReviews / minimumReviews) * 100)
    : 0;
  const modelPredictions = new Map(
    forecast.model.pending_predictions.map((prediction) => [
      `${prediction.region_code}|${prediction.window_start}`,
      prediction,
    ]),
  );

  return (
    <main className="admin-page">
      <header className="site-header">
        <Link className="brand" href="/" aria-label="CrisisPulse dashboard home">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>CrisisPulse</span>
        </Link>
        <nav className="header-nav" aria-label="Primary navigation">
          <Link href="/">Dashboard</Link>
          <Link className="active" href="/admin">Admin</Link>
        </nav>
        <div className="header-meta">
          <span className={connection === "ready" ? "live-dot" : "live-dot snapshot"} aria-hidden="true" />
          {connection === "ready" ? "Live operations" : connection === "loading" ? "Checking operations" : "Verified snapshot"}
          <strong>{formatEastern(snapshot.window_end)}</strong>
        </div>
      </header>

      <nav className="mobile-section-nav" aria-label="Admin sections">
        <a href="#status">Status</a>
        <a href="#operations">Operations</a>
        <a href="#admin-forecast">Forecasts</a>
        <a href="#article-quality">Quality</a>
      </nav>

      <section className="admin-hero" id="status">
        <div className="admin-hero-copy">
          <p className="eyebrow">Operations console</p>
          <h1>Know what is working before customers do.</h1>
          <p>
            One private view for data freshness, forecasts, model health, human
            review, and the work remaining before a reliable paid pilot.
          </p>
        </div>
        <aside className={`admin-health ${refreshHealthy ? "healthy" : "attention"}`} aria-label="Current system health">
          <span><i className="admin-status-dot" /> Current status</span>
          <strong>{overallStatus}</strong>
          <p>
            {adminStatus
              ? `Last successful refresh ${formatEastern(adminStatus.refresh.last_success_at)}.`
              : `Latest retained data ${formatEastern(snapshot.window_end)}.`}
            {" "}Times are shown in U.S. Eastern Time.
          </p>
          <button className="admin-check-button" disabled={checking} onClick={() => void refreshAdmin()} type="button">
            {checking ? "Checking…" : "Check now"}
          </button>
        </aside>
      </section>

      <section className="admin-summary" aria-label="Operations summary">
        <article>
          <span>Refresh health</span>
          <strong>{adminStatus ? `${adminStatus.refresh.age_minutes}m` : "—"}</strong>
          <small>{refreshHealthy ? "Since last success" : "Waiting for live status"}</small>
        </article>
        <article>
          <span>Open forecasts</span>
          <strong>{forecast.pending_predictions.length}</strong>
          <small>Future outcomes still collecting</small>
        </article>
        <article>
          <span>Article reviews</span>
          <strong>{resolvedReviews}/{minimumReviews}</strong>
          <small>{qualitySampleReady ? "Balanced quality rates unlocked" : qualityBalancePending ? "Strong and blocked review balance still needed" : `${remainingReviews} until the total minimum; balance also required`}</small>
        </article>
        <article>
          <span>Model holdout</span>
          <strong>{forecast.model.test_hours}h</strong>
          <small>{formatNumber(forecast.model.test_rows)} later rows</small>
        </article>
      </section>

      <section className="admin-overview" id="operations">
        <article className="admin-surface">
          <div className="admin-section-heading">
            <div><p className="eyebrow">Operating checks</p><h2>Live system checklist</h2></div>
            <span className={refreshHealthy ? "admin-pill ready" : "admin-pill"}>{refreshHealthy ? "Healthy" : "Check status"}</span>
          </div>
          <p>The page checks the local API every minute. No operational control here can alter or delete data.</p>
          <ul className="admin-checks">
            <li><i className={connection === "ready" ? "" : "waiting"} /><strong>Local API</strong><span>{connection === "ready" ? "Connected" : "Snapshot fallback"}</span></li>
            <li><i className={refreshHealthy ? "" : "waiting"} /><strong>15-minute data refresh</strong><span>{adminStatus ? adminStatus.refresh.message : "Status unavailable"}</span></li>
            <li><i /><strong>Dashboard snapshot</strong><span>{formatEastern(snapshot.window_end)}</span></li>
            <li><i className={modelReady ? "" : "waiting"} /><strong>Chronological model</strong><span>{modelReady ? "Benchmark ready" : "Unavailable"}</span></li>
            <li><i className={qualitySampleReady ? "" : "waiting"} /><strong>Article filter evaluation</strong><span>{resolvedReviews} of {minimumReviews} resolved</span></li>
          </ul>
          <div className="admin-detail-grid">
            <div><span>Next refresh expected</span><strong>{adminStatus ? formatEastern(adminStatus.refresh.expected_next_refresh_at) : "—"}</strong></div>
            <div><span>Files processed last run</span><strong>{adminStatus?.refresh.processed_files ?? "—"}</strong></div>
            <div>
              <span>Permanent article archive</span>
              <strong>{adminStatus?.refresh.archived_articles !== undefined ? formatNumber(adminStatus.refresh.archived_articles) : "—"}</strong>
              <small>{adminStatus ? `${formatBytes(adminStatus.refresh.article_archive_bytes)} compressed · ${formatNumber(adminStatus.refresh.new_archived_articles ?? 0)} new last run` : "Preserved before raw rotation"}</small>
              <small>{adminStatus ? `${formatNumber(adminStatus.refresh.title_backfill_updated_articles ?? 0)} titles added last run · ${formatNumber(adminStatus.refresh.title_backfill_remaining_articles ?? 0)} remaining` : "Gradual title backfill pending"}</small>
            </div>
            <div>
              <span>Raw archive usage</span>
              <strong>{adminStatus ? `${formatBytes(adminStatus.refresh.retained_raw_bytes)} / ${formatBytes(adminStatus.refresh.raw_storage_limit_bytes)}` : "—"}</strong>
              <small>{adminStatus ? `${formatNumber(adminStatus.refresh.retained_raw_files)} files retained` : "10 GB storage budget"}</small>
            </div>
          </div>
        </article>

        <aside className="admin-surface admin-readiness">
          <p className="eyebrow">Paid pilot readiness</p>
          <h2>{qualitySampleReady ? "Two foundations are still open." : "Three foundations are still open."}</h2>
          <p>{qualitySampleReady ? "The first balanced article evidence sample is complete. Reliable hosting and private authentication remain." : "Article-filter evidence can now be collected here. Reliable hosting and private authentication follow."}</p>
          <ol className="readiness-list">
            <li className="done"><span>01</span><div><strong>Automated collection</strong><small>Running every 15 minutes</small></div></li>
            <li className={qualitySampleReady ? "done" : "current"}><span>02</span><div><strong>Article filter evidence</strong><small>{qualitySampleReady ? "Balanced minimum reached" : qualityBalancePending ? "Balance strong and blocked reviews" : `${remainingReviews} resolved reviews remaining; balance required`}</small></div></li>
            <li><span>03</span><div><strong>Reliable cloud server</strong><small>Deployment package not started</small></div></li>
            <li><span>04</span><div><strong>Private customer access</strong><small>Required before this page goes online</small></div></li>
          </ol>
        </aside>
      </section>

      <section className="admin-forecast-section" id="admin-forecast" aria-labelledby="admin-forecast-heading">
        <div className="admin-section-heading">
          <div>
            <p className="eyebrow">Forecast operations</p>
            <h2 id="admin-forecast-heading">Open clocks and model benchmark</h2>
          </div>
          <span className="admin-pill ready">Read-only</span>
        </div>
        <div className="admin-forecast-grid">
          <article className="admin-surface admin-forecast-table">
            {forecast.pending_predictions.length > 0 ? (
              <div className="admin-table-wrap">
                <table className="admin-forecast-mobile-table">
                  <thead><tr><th>Region</th><th>Detected</th><th>Outcome closes</th><th>Remaining</th><th>Model score</th></tr></thead>
                  <tbody>
                    {forecast.pending_predictions.map((prediction) => {
                      const modelPrediction = modelPredictions.get(`${prediction.region_code}|${prediction.window_start}`);
                      return (
                        <tr key={`${prediction.region_code}|${prediction.window_start}`}>
                          <td data-label="Region"><strong>{prediction.region_code}</strong><small>{prediction.stories_at_detection} stories · {prediction.domains_at_detection} domains</small></td>
                          <td data-label="Detected">{formatEastern(prediction.window_start)}</td>
                          <td data-label="Outcome closes">{formatEastern(prediction.matures_at)}</td>
                          <td data-label="Remaining"><span className="admin-countdown">{prediction.hours_remaining}h</span></td>
                          <td data-label="Model score">{modelPrediction ? `${(modelPrediction.model_score * 100).toFixed(1)} / 100` : "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : <p className="admin-empty">No forecast outcomes are currently pending.</p>}
          </article>

          <aside className="admin-model-card">
            <span>Later holdout</span>
            <strong>{formatPercent(forecast.model.test_metrics.average_precision)}</strong>
            <small>Average precision</small>
            <dl>
              <div><dt>Alert precision</dt><dd>{formatPercent(forecast.model.test_metrics.precision)}</dd></div>
              <div><dt>Outcome recall</dt><dd>{formatPercent(forecast.model.test_metrics.recall)}</dd></div>
              <div><dt>False alerts/day</dt><dd>{forecast.model.test_metrics.false_alerts_per_day?.toFixed(1) ?? "—"}</dd></div>
              <div><dt>Test positives</dt><dd>{forecast.model.test_positives}</dd></div>
            </dl>
            <p>Exploratory media-spread benchmark—not disaster probability or production validation.</p>
          </aside>
        </div>
      </section>

      <section className="admin-quality-section" id="article-quality" aria-labelledby="article-quality-heading">
        <div className="admin-section-heading admin-quality-heading">
          <div>
            <p className="eyebrow">Article filter validation</p>
            <h2 id="article-quality-heading">Review real examples—even when there are no alerts.</h2>
            <p>A balanced daily sample measures strong flood matches separately from stories the safety filters blocked.</p>
          </div>
          <a className="export-link" download="crisispulse-article-quality-reviews.csv" href={qualityExportURL}>
            Download reviews (.csv) <span aria-hidden="true">↓</span>
          </a>
        </div>

        <div className="admin-quality-overview">
          <article className="admin-review-progress">
            <div>
              <p className="eyebrow">Measurement progress</p>
              <h3>{qualitySampleReady ? "First filter measurements are ready." : "Rates stay locked until the sample is credible."}</h3>
            </div>
            <div className="admin-review-meter">
              <div><strong>{resolvedReviews}</strong><span>resolved article labels</span></div>
              <span className="admin-meter" role="progressbar" aria-label="Resolved article-review progress" aria-valuemin={0} aria-valuemax={minimumReviews} aria-valuenow={resolvedReviews}><i style={{ width: `${qualityProgress}%` }} /></span>
              <small>{qualitySampleReady ? "Balanced strong and blocked minimum reached." : qualityBalancePending ? "Total minimum reached; strong and blocked labels still need balance." : `${remainingReviews} more relevant or not-relevant decisions needed, balanced across strong and blocked matches.`}</small>
            </div>
          </article>
          <aside className="admin-quality-results">
            <div><span>Strong-match relevance</span><strong>{formatPercent(qualitySummary?.high_match_precision)}</strong><small>{qualitySummary?.high_resolved ?? 0} strong matches resolved</small></div>
            <div><span>Relevant among blocked</span><strong>{formatPercent(qualitySummary?.weak_match_relevant_rate)}</strong><small>{qualitySummary?.weak_resolved ?? 0} blocked matches resolved</small></div>
            <p>Because this sample is deliberately balanced, these are separate filter checks—not an overall accuracy claim.</p>
          </aside>
        </div>

        <ol className="admin-quality-guide" aria-label="How to review an article">
          <li><span>01</span><div><strong>Open the publisher story</strong><small>Use the headline link and read enough to identify the actual subject.</small></div></li>
          <li><span>02</span><div><strong>Judge physical flooding</strong><small>Choose Relevant flood only when the article describes a real flood, flooding, or flood response.</small></div></li>
          <li><span>03</span><div><strong>Keep uncertainty honest</strong><small>Choose Not relevant for metaphorical or unrelated stories; use Uncertain when the evidence is insufficient.</small></div></li>
        </ol>

        {qualityNotice ? (
          <p
            aria-atomic="true"
            className={`quality-review-notice ${qualityNotice.kind}`}
            role={qualityNotice.kind === "error" ? "alert" : "status"}
          >
            <strong>{qualityNotice.kind === "success" ? "Answer saved" : "Not saved"}</strong>
            <span>{qualityNotice.message}</span>
          </p>
        ) : null}

        {qualitySample?.articles?.length ? (
          <div className="quality-queue-toolbar">
            <p><strong>{pendingQualityArticles.length}</strong><span>{pendingQualityArticles.length === 1 ? "article needs review" : "articles need review"}</span></p>
            {reviewedQualityArticles.length ? (
              <button
                aria-expanded={showReviewedArticles}
                onClick={() => setShowReviewedArticles((current) => !current)}
                type="button"
              >
                {showReviewedArticles ? "Hide reviewed" : `Show reviewed (${reviewedQualityArticles.length})`}
              </button>
            ) : null}
          </div>
        ) : null}

        {qualitySample?.articles?.length && visibleQualityArticles.length ? (
          <div className="article-quality-grid">
            {visibleQualityArticles.map((article) => {
              const link = safeArticleURL(article.url);
              const isSaving = savingArticleReview?.articleID === article.article_id;
              const activeDecision = isSaving ? savingArticleReview?.decision : article.decision;
              const bucketLabel = article.review_bucket === "high_match"
                ? "Strong match"
                : article.review_bucket === "headline_conflict"
                  ? "Headline conflict"
                  : "Ambiguous match";
              return (
                <article
                  aria-busy={isSaving}
                  className={`article-quality-card${isSaving ? " saving" : ""}${article.decision ? " reviewed" : ""}`}
                  key={article.article_id}
                >
                  <header>
                    <span className={`quality-strength ${article.match_strength}`}>{bucketLabel}</span>
                    <span className={activeDecision ? `decision-chip ${activeDecision === "relevant" ? "confirmed" : activeDecision === "not_relevant" ? "irrelevant" : "uncertain"}` : "decision-chip pending"}>
                      {isSaving ? "Saving answer" : activeDecision === "relevant" ? "Relevant" : activeDecision === "not_relevant" ? "Not relevant" : activeDecision === "uncertain" ? "Uncertain" : "Needs review"}
                    </span>
                  </header>
                  {link ? <a className="article-quality-title" href={link} rel="noopener noreferrer" target="_blank">{article.title} <span aria-hidden="true">↗</span></a> : <strong className="article-quality-title">{article.title}</strong>}
                  <small className={`article-title-source ${article.title_source ?? "legacy"}`}>
                    {article.title_source === "manual_override"
                      ? "Manually verified publisher title"
                      : article.title_source === "publisher_metadata"
                      ? "Publisher-provided title"
                      : article.title_source === "url_path"
                        ? "Cleaned from publisher URL"
                        : article.title_source === "unavailable"
                          ? "No trustworthy title available"
                          : "Title source not recorded"}
                  </small>
                  <p>{article.review_reason}</p>
                  <dl>
                    <div><dt>Publisher</dt><dd>{article.source_domain || "Unknown"}</dd></div>
                    <div><dt>Location</dt><dd>{article.location_name || "Not confidently assigned"}</dd></div>
                    <div><dt>Seen</dt><dd>{formatEastern(article.seen_at)}</dd></div>
                  </dl>
                  <div className="quality-theme-list">
                    {article.themes.slice(0, 2).map((theme) => <span key={theme}>{theme.replaceAll("_", " ")}</span>)}
                  </div>
                  {isSaving ? <p className="article-review-state" role="status">Saving this answer…</p> : null}
                  <div className="review-actions" aria-label={`Review ${article.title}`}>
                    {articleReviewOptions.map((option) => (
                      <button
                        aria-pressed={activeDecision === option.value}
                        className={`review-button ${option.tone}${activeDecision === option.value ? " selected" : ""}`}
                        disabled={connection !== "ready" || savingArticleReview !== null}
                        key={option.value}
                        onClick={() => void saveArticleReview(article, option.value)}
                        type="button"
                      >
                        {isSaving && savingArticleReview?.decision === option.value ? "Saving…" : option.label}
                      </button>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        ) : qualitySample?.articles?.length ? (
          <div className="admin-surface quality-all-reviewed">
            <span aria-hidden="true">✓</span>
            <div><strong>Today’s review queue has no pending cards.</strong><p>Every sampled article has an answer. Overall measurements unlock only after a balanced sample; use Show reviewed if you need to correct one.</p></div>
          </div>
        ) : (
          <div className="admin-surface admin-empty">The first archive-backed daily sample will appear after the next refresh.</div>
        )}

        <aside className="admin-quality-safety">
          <strong>Safe by design.</strong>
          <span>Review decisions are append-only. This page cannot delete data, restart services, change billing, or issue an emergency warning.</span>
          <small>{qualitySample ? `${formatNumber(qualitySample.articles.length)} articles sampled from ${formatNumber(qualitySample.archive_articles)} permanently archived records on ${qualitySample.sample_date}.` : "Waiting for a live sample."}</small>
        </aside>
      </section>
    </main>
  );
}
