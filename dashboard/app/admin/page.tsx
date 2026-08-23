"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import bundledDashboardData from "../../data/dashboard.json";

type DashboardData = typeof bundledDashboardData;
type ReviewSummary = {
  total_reviews: number;
  confirmed_events: number;
  irrelevant_news: number;
  uncertain: number;
  resolved_reviews: number;
  minimum_sample: number;
  remaining_to_sample: number;
  confirmed_event_rate: number | null;
  irrelevant_news_rate: number | null;
  status: "collecting_labels" | "sample_ready";
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
  const [reviewSummary, setReviewSummary] = useState<ReviewSummary | null>(null);
  const [adminStatus, setAdminStatus] = useState<AdminStatus | null>(null);
  const [connection, setConnection] = useState<"loading" | "ready" | "offline">("loading");
  const [checking, setChecking] = useState(false);
  const requestInFlight = useRef(false);
  const { snapshot, forecast } = dashboardData;

  const refreshAdmin = useCallback(async (signal?: AbortSignal) => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    setChecking(true);
    try {
      const options: RequestInit = { cache: "no-store", signal };
      const [snapshotResult, statusResult, reviewResult] = await Promise.allSettled([
        fetch("/api/v1/snapshot", options),
        fetch("/api/v1/admin/status", options),
        fetch("/api/v1/reviews/summary", options),
      ]);
      const [nextData, nextStatus, nextReview] = await Promise.all([
        settledJSON<DashboardData>(snapshotResult),
        settledJSON<AdminStatus>(statusResult),
        settledJSON<ReviewSummary>(reviewResult),
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
      if (nextReview) setReviewSummary(nextReview);
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

  const modelReady = forecast.model.status === "ready";
  const refreshHealthy = connection === "ready" && adminStatus?.refresh.health === "healthy";
  const overallStatus = refreshHealthy && modelReady ? "Operating normally" : connection === "offline" ? "Local API offline" : "Attention needed";
  const resolvedReviews = reviewSummary?.resolved_reviews ?? 0;
  const minimumReviews = reviewSummary?.minimum_sample ?? 20;
  const reviewProgress = minimumReviews > 0
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
        <a href="#admin-review">Reviews</a>
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
          <span>Resolved reviews</span>
          <strong>{resolvedReviews}/{minimumReviews}</strong>
          <small>{Math.max(0, minimumReviews - resolvedReviews)} until quality rates unlock</small>
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
            <li><i className={resolvedReviews >= minimumReviews ? "" : "waiting"} /><strong>Human evaluation sample</strong><span>{resolvedReviews} of {minimumReviews} resolved</span></li>
          </ul>
          <div className="admin-detail-grid">
            <div><span>Next refresh expected</span><strong>{adminStatus ? formatEastern(adminStatus.refresh.expected_next_refresh_at) : "—"}</strong></div>
            <div><span>Files processed last run</span><strong>{adminStatus?.refresh.processed_files ?? "—"}</strong></div>
            <div>
              <span>Permanent article archive</span>
              <strong>{adminStatus?.refresh.archived_articles !== undefined ? formatNumber(adminStatus.refresh.archived_articles) : "—"}</strong>
              <small>{adminStatus ? `${formatBytes(adminStatus.refresh.article_archive_bytes)} compressed · ${formatNumber(adminStatus.refresh.new_archived_articles ?? 0)} new last run` : "Preserved before raw rotation"}</small>
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
          <h2>Two foundations are still open.</h2>
          <p>The product evidence is growing automatically. Reliable hosting and private authentication are the remaining infrastructure gates.</p>
          <ol className="readiness-list">
            <li className="done"><span>01</span><div><strong>Automated collection</strong><small>Running every 15 minutes</small></div></li>
            <li className={resolvedReviews >= minimumReviews ? "done" : "current"}><span>02</span><div><strong>Human evidence sample</strong><small>{resolvedReviews >= minimumReviews ? "Minimum reached" : `${minimumReviews - resolvedReviews} resolved reviews remaining`}</small></div></li>
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

      <section className="admin-review-section" id="admin-review">
        <article className="admin-review-progress">
          <div><p className="eyebrow">Human evidence</p><h2>Quality rates stay locked until the sample is credible.</h2></div>
          <div className="admin-review-meter">
            <div><strong>{resolvedReviews}</strong><span>resolved labels</span></div>
            <span className="admin-meter" role="progressbar" aria-label="Resolved review progress" aria-valuemin={0} aria-valuemax={minimumReviews} aria-valuenow={resolvedReviews}><i style={{ width: `${reviewProgress}%` }} /></span>
            <small>{Math.max(0, minimumReviews - resolvedReviews)} more real-event or irrelevant-news decisions needed.</small>
          </div>
        </article>
        <aside className="admin-surface admin-safety">
          <p className="eyebrow">Admin safety</p>
          <h2>Read-only by design.</h2>
          <p>No restart, deletion, billing, or customer-access controls are exposed in this local page.</p>
          <div className="admin-safety-note">
            Before this goes online, the admin route must sit behind private authentication. CrisisPulse remains a news-monitoring product—not an emergency warning system.
          </div>
        </aside>
      </section>
    </main>
  );
}
