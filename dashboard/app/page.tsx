"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import bundledDashboardData from "../data/dashboard.json";

type EvidenceSource = { domain: string; url: string };
type EvidenceStory = {
  story_id: string;
  seen_at: string;
  location: string | null;
  themes: string[];
  sources: EvidenceSource[];
  title?: string | null;
};
type PendingForecast = {
  region_code: string;
  window_start: string;
  matures_at: string;
  hours_remaining: number;
  stories_at_detection: number;
  domains_at_detection: number;
};
type ForecastModelMetrics = {
  average_precision: number | null;
  brier_score: number | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  predicted_alerts: number;
  false_alerts_per_day: number | null;
};
type PendingModelPrediction = {
  region_code: string;
  window_start: string;
  model_score: number;
  clears_alert_threshold: boolean;
};
type ForecastModel = {
  status: "ready" | "unavailable";
  type: string;
  decision_threshold: number | null;
  scores_are_calibrated_probabilities: boolean;
  training_rows: number;
  validation_rows: number;
  test_rows: number;
  test_positives: number;
  validation_hours: number;
  test_hours: number;
  validation_metrics: Partial<ForecastModelMetrics>;
  test_metrics: Partial<ForecastModelMetrics>;
  test_window: { prediction_start?: string; prediction_end?: string };
  pending_predictions: PendingModelPrediction[];
  guardrails: string[];
};
type ForecastSummary = {
  target: {
    name: string;
    horizon_hours: number;
    domain_threshold: number;
    definition: string;
  };
  eligible_windows: number;
  positive_outcomes: number;
  evaluation_ready_windows: number;
  candidate_predictions: number;
  evaluated_predictions: number;
  pending_predictions: PendingForecast[];
  precision: number | null;
  recall: number | null;
  model: ForecastModel;
};
type BundledSignal = (typeof bundledDashboardData)["signals"][number];
type Signal = Omit<BundledSignal, "evidence"> & { evidence: EvidenceStory[] };
type DashboardData = Omit<typeof bundledDashboardData, "signals" | "forecast"> & {
  signals: Signal[];
  forecast: ForecastSummary;
  latest_coverage?: EvidenceStory[];
};
type ReviewDecision = "confirmed_event" | "irrelevant_news" | "uncertain";
type ReviewRecord = {
  signal_id: string;
  region_code: string;
  window_start: string;
  decision: ReviewDecision;
  reviewed_at: string;
};
type ReviewsResponse = { reviews: ReviewRecord[] };
type ReviewResponse = { review: ReviewRecord };
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

const snapshotURL = "/api/v1/snapshot";
const reviewsURL = "/api/v1/reviews";
const reviewSummaryURL = "/api/v1/reviews/summary";
const reviewExportURL = "/api/v1/reviews/export.csv";

const reviewOptions: Array<{
  value: ReviewDecision;
  label: string;
  shortLabel: string;
  tone: string;
}> = [
  { value: "confirmed_event", label: "Real event", shortLabel: "Real event", tone: "confirmed" },
  { value: "irrelevant_news", label: "Irrelevant news", shortLabel: "Irrelevant", tone: "irrelevant" },
  { value: "uncertain", label: "Uncertain", shortLabel: "Uncertain", tone: "uncertain" },
];

const formatNumber = (value: number) => value.toLocaleString("en-US");
const formatScore = (value: number | null) => {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`.replace("-", "−");
};
const headlineAcronyms: Record<string, string> = {
  abc: "ABC",
  ai: "AI",
  bbc: "BBC",
  cbs: "CBS",
  cnn: "CNN",
  csc: "CSC",
  fema: "FEMA",
  gdelt: "GDELT",
  nasa: "NASA",
  nbc: "NBC",
  nj: "NJ",
  noaa: "NOAA",
  nws: "NWS",
  nyc: "NYC",
  usa: "USA",
  ust: "UST",
};
const preserveHeadlineAcronyms = (value: string, includeUS = false) =>
  value.replace(/\b[A-Za-z][A-Za-z0-9]*\b/g, (word) => {
    const lowered = word.toLowerCase();
    if (includeUS && lowered === "us") return "US";
    return headlineAcronyms[lowered] ?? word;
  });
const sourceLabel = (source: EvidenceSource) => {
  try {
    const parsed = new URL(source.url);
    const segments = parsed.pathname.split("/").filter(Boolean).reverse();
    for (const segment of segments) {
      const decoded = decodeURIComponent(segment)
        .replace(/\.(?:html?|aspx?|php)$/i, "")
        .trim();
      if (!decoded || /^\d+$/.test(decoded)) continue;
      if (/^(?:article[-_]?)?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(decoded)) continue;
      const words = decoded.match(/[A-Za-zÀ-ÖØ-öø-ÿ]+/g) ?? [];
      if (words.length < 2) continue;
      const readable = decoded.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
      if (readable) {
        const titleCased = readable.replace(/\b\w/g, (letter) => letter.toUpperCase());
        return preserveHeadlineAcronyms(titleCased, true);
      }
    }
    return `Open article from ${source.domain}`;
  } catch {
    return source.domain;
  }
};
const safePublisherURL = (value: string) => {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
};
const publisherDomain = (source: EvidenceSource) => {
  const safeURL = safePublisherURL(source.url);
  if (!safeURL) return null;
  return new URL(safeURL).hostname.replace(/^www\./i, "");
};
const coverageConfidence = (publisherCount: number) => {
  if (publisherCount >= 3) return "Multi-source coverage";
  if (publisherCount === 2) return "Corroborated coverage";
  return "Single publisher";
};
const storyHeadline = (story: EvidenceStory, source: EvidenceSource) =>
  story.title
    ? preserveHeadlineAcronyms(story.title)
    : sourceLabel(source);
const themeLabel = (theme: string) => {
  const readable = theme
    .replace(/^NATURAL_DISASTER_/, "")
    .replaceAll("_", " ")
    .toLowerCase();
  return `GDELT tag: ${readable.charAt(0).toUpperCase() + readable.slice(1)}`;
};
const signalID = (signal: Signal) => `${signal.code}|${signal.window_start}`;
const formatSignalScore = (signal: Signal) =>
  signal.score === null && signal.status === "candidate_anomaly"
    ? "Zero-baseline jump"
    : formatScore(signal.score);
const formatWindow = (value: string) => {
  const date = new Date(value.endsWith("Z") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  });
};

const statusRows = [
  { key: "insufficient_history", label: "Building history", tone: "waiting" },
  { key: "below_minimum_support", label: "Below evidence minimum", tone: "quiet" },
  { key: "normal", label: "Normal", tone: "normal" },
  { key: "candidate_anomaly", label: "Candidate anomaly", tone: "alert" },
] as const;

export default function Home() {
  const [dashboardData, setDashboardData] = useState<DashboardData>(
    bundledDashboardData as DashboardData,
  );
  const [dataSource, setDataSource] = useState<"api" | "snapshot">("snapshot");
  const [reviews, setReviews] = useState<Record<string, ReviewRecord>>({});
  const [reviewSummary, setReviewSummary] = useState<ReviewSummary | null>(null);
  const [reviewConnection, setReviewConnection] = useState<"loading" | "ready" | "unavailable">("loading");
  const [savingReview, setSavingReview] = useState<{ signalID: string; decision: ReviewDecision } | null>(null);
  const [reviewNotice, setReviewNotice] = useState<string | null>(null);
  const { snapshot, signals, parameters, status_counts: statusCounts, forecast } = dashboardData;
  const latestCoverage = (Array.isArray(dashboardData.latest_coverage)
    ? dashboardData.latest_coverage
    : [])
    .map((story) => ({
      ...story,
      sources: Array.isArray(story.sources)
        ? story.sources.filter((source) => safePublisherURL(source.url))
        : [],
    }))
    .filter((story) => story.sources.length > 0)
    .slice(0, 6);
  const hasCandidates = snapshot.candidates > 0;
  const candidateSignals = signals.filter((signal) => signal.status === "candidate_anomaly");
  const reviewedCount = candidateSignals.filter((signal) => reviews[signalID(signal)]).length;
  const sampleProgress = reviewSummary
    ? Math.min(100, (reviewSummary.resolved_reviews / reviewSummary.minimum_sample) * 100)
    : 0;
  const outcomeBaseRate = forecast.eligible_windows > 0
    ? forecast.positive_outcomes / forecast.eligible_windows
    : null;
  const modelPredictions = new Map(
    forecast.model.pending_predictions.map((prediction) => [
      `${prediction.region_code}|${prediction.window_start}`,
      prediction,
    ]),
  );
  const barWidth = (count: number) =>
    count <= 0 || snapshot.scored_rows <= 0
      ? "0%"
      : `${Math.min(100, Math.max(3, (count / snapshot.scored_rows) * 100))}%`;

  useEffect(() => {
    const controller = new AbortController();
    fetch(snapshotURL, { cache: "no-store", signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`API returned ${response.status}`);
        return response.json() as Promise<DashboardData>;
      })
      .then((nextData) => {
        if (!nextData.snapshot || !Array.isArray(nextData.signals)) {
          throw new Error("API response is missing dashboard fields");
        }
        setDashboardData((current) => ({
          ...nextData,
          latest_coverage: Array.isArray(nextData.latest_coverage)
            ? nextData.latest_coverage
            : current.latest_coverage,
        }));
        setDataSource("api");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setDataSource("snapshot");
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch(reviewsURL, { cache: "no-store", signal: controller.signal }),
      fetch(reviewSummaryURL, { cache: "no-store", signal: controller.signal }),
    ])
      .then(async ([reviewsResponse, summaryResponse]) => {
        if (!reviewsResponse.ok || !summaryResponse.ok) {
          throw new Error("Review API is unavailable");
        }
        return Promise.all([
          reviewsResponse.json() as Promise<ReviewsResponse>,
          summaryResponse.json() as Promise<ReviewSummary>,
        ]);
      })
      .then(([payload, summary]) => {
        const latest = Object.fromEntries(
          payload.reviews.map((review) => [review.signal_id, review]),
        );
        setReviews(latest);
        setReviewSummary(summary);
        setReviewConnection("ready");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setReviewConnection("unavailable");
        }
      });
    return () => controller.abort();
  }, []);

  const saveReview = async (signal: Signal, decision: ReviewDecision) => {
    const id = signalID(signal);
    setSavingReview({ signalID: id, decision });
    setReviewNotice(null);
    try {
      const response = await fetch(reviewsURL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          region_code: signal.code,
          window_start: signal.window_start,
          decision,
        }),
      });
      if (!response.ok) throw new Error(`Review API returned ${response.status}`);
      const payload = await response.json() as ReviewResponse;
      setReviews((current) => ({ ...current, [payload.review.signal_id]: payload.review }));
      const summaryResponse = await fetch(reviewSummaryURL, { cache: "no-store" });
      if (summaryResponse.ok) {
        setReviewSummary(await summaryResponse.json() as ReviewSummary);
      }
      setReviewConnection("ready");
      const choice = reviewOptions.find((option) => option.value === decision);
      setReviewNotice(`Saved “${choice?.label ?? decision}” for ${signal.region}.`);
    } catch {
      setReviewConnection("unavailable");
      setReviewNotice("The decision could not be saved. Check that the local API is running.");
    } finally {
      setSavingReview(null);
    }
  };

  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="CrisisPulse dashboard home">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>CrisisPulse</span>
        </a>
        <nav className="header-nav" aria-label="Primary navigation">
          <Link className="active" href="/">Dashboard</Link>
          <Link href="/admin">Admin</Link>
        </nav>
        <div className="header-meta">
          <span className={dataSource === "api" ? "live-dot" : "live-dot snapshot"} aria-hidden="true" />
          {dataSource === "api" ? "Live API connected" : "Verified local snapshot"}
          <strong>{formatWindow(snapshot.window_end)}</strong>
        </div>
      </header>

      <nav className="mobile-section-nav" aria-label="Dashboard sections">
        <a href="#top">Overview</a>
        <a href="#coverage">Coverage</a>
        <a href="#review">Review</a>
        <a href="#forecast">Forecast</a>
        <a href="#signals">Signals</a>
      </nav>

      <section className="hero" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Global flood reporting monitor</p>
          <h1>
            {hasCandidates
              ? `${snapshot.candidates} unusual reporting ${snapshot.candidates === 1 ? "signal needs" : "signals need"} review.`
              : "No unusual reporting signals right now."}
          </h1>
          <p className="lede">
            CrisisPulse reviewed {snapshot.window_label} of GDELT news activity.
            {hasCandidates
              ? " These candidates passed the history and source-diversity gates and now need evidence review."
              : " The latest eligible scoring hour opened cleanly, with no candidate alerts."}
          </p>
          <div className="notice" role="status">
            <span className={hasCandidates ? "notice-icon alert" : "notice-icon"} aria-hidden="true">
              {hasCandidates ? "!" : "✓"}
            </span>
            <span>
              <strong>{hasCandidates ? "Evidence review required." : "System behaving as designed."}</strong>
              {hasCandidates
                ? "A candidate is an unusual news pattern, not proof of a physical disaster."
                : "The history gate did not turn ordinary coverage into an alert."}
            </span>
          </div>
        </div>

        <aside className="watch-panel" aria-label="Current watch status">
          <p className="panel-label">Current watch</p>
          <div className="watch-count">{formatNumber(snapshot.candidates)}</div>
          <p className="watch-title">Candidate anomalies</p>
          <div className="watch-rule" />
          <dl className="watch-details">
            <div><dt>Minimum history</dt><dd>{parameters.minimum_history_hours} hours</dd></div>
            <div><dt>Minimum evidence</dt><dd>{parameters.minimum_stories} stories · {parameters.minimum_domains} domains</dd></div>
            <div><dt>Alert threshold</dt><dd>z ≥ {parameters.z_threshold.toFixed(1)} or a gated zero-baseline jump</dd></div>
          </dl>
        </aside>
      </section>

      <section className="metrics" aria-label="Data coverage">
        <article>
          <p>Flood articles retained</p>
          <strong>{formatNumber(snapshot.clean_articles)}</strong>
          <span>After exact duplicate removal</span>
        </article>
        <article>
          <p>Regions observed</p>
          <strong>{formatNumber(snapshot.regions)}</strong>
          <span>Named and unresolved regions</span>
        </article>
        <article>
          <p>Hourly windows</p>
          <strong>{formatNumber(snapshot.hours)}</strong>
          <span>{snapshot.window_label}</span>
        </article>
        <article>
          <p>Hourly story groups</p>
          <strong>{formatNumber(snapshot.story_groups)}</strong>
          <span>Distinct within each region and hour</span>
        </article>
      </section>

      <section className="coverage-section" id="coverage" aria-labelledby="coverage-heading">
        <div className="coverage-heading">
          <div>
            <p className="eyebrow">Publisher evidence</p>
            <h2 id="coverage-heading">Latest flood coverage</h2>
            <p>
              Recent publisher reports that passed CrisisPulse&apos;s flood-topic checks.
              These links are evidence, not automatic confirmation of a physical incident.
            </p>
          </div>
          <div className="coverage-count" aria-label={`${latestCoverage.length} recent story groups`}>
            <strong>{latestCoverage.length}</strong>
            <span>recent story {latestCoverage.length === 1 ? "group" : "groups"}</span>
          </div>
        </div>

        {latestCoverage.length > 0 ? (
          <div className="coverage-grid">
            {latestCoverage.map((story) => {
              const primarySource = story.sources[0];
              const primaryURL = safePublisherURL(primarySource.url);
              const domains = Array.from(new Set(
                story.sources.map(publisherDomain).filter((domain): domain is string => Boolean(domain)),
              ));
              return (
                <article className="coverage-card" key={`${story.story_id}-${story.seen_at}`}>
                  <header>
                    <span className={domains.length > 1 ? "coverage-badge corroborated" : "coverage-badge"}>
                      {coverageConfidence(domains.length)}
                    </span>
                    <time dateTime={story.seen_at}>{formatWindow(story.seen_at)}</time>
                  </header>
                  <a className="coverage-title" href={primaryURL ?? undefined} rel="noopener noreferrer" target="_blank">
                    {storyHeadline(story, primarySource)} <span aria-hidden="true">↗</span>
                  </a>
                  <div className="coverage-context">
                    <span>{story.location || "Location unresolved"}</span>
                    {story.themes.slice(0, 2).map((theme) => (
                      <span key={theme}>{themeLabel(theme).replace("GDELT tag: ", "")}</span>
                    ))}
                  </div>
                  <footer className="coverage-source">
                    <span>{domains.length > 1 ? `${domains.length} independent publishers` : domains[0]}</span>
                    <a href={primaryURL ?? undefined} rel="noopener noreferrer" target="_blank">Read publisher report</a>
                  </footer>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="coverage-empty">
            <span aria-hidden="true">✓</span>
            <div>
              <strong>No recent eligible coverage in this window.</strong>
              <p>The feed will fill automatically when the next checked flood reports arrive.</p>
            </div>
          </div>
        )}
      </section>

      <section className="review-section" id="review" aria-labelledby="review-heading">
        <div className="review-heading">
          <div>
            <p className="eyebrow">Human validation</p>
            <h2 id="review-heading">Review queue</h2>
            <p>
              Label unusual reporting so CrisisPulse can separate credible events
              from irrelevant coverage and ambiguous evidence.
            </p>
          </div>
          <span className={reviewedCount === candidateSignals.length && candidateSignals.length > 0 ? "review-progress complete" : "review-progress"}>
            {reviewedCount} of {candidateSignals.length} labeled
          </span>
        </div>

        {reviewNotice ? <p className="review-notice" role="status">{reviewNotice}</p> : null}

        {candidateSignals.length > 0 ? (
          <div className="review-grid">
            {candidateSignals.map((signal) => {
              const id = signalID(signal);
              const currentReview = reviews[id];
              const currentOption = reviewOptions.find(
                (option) => option.value === currentReview?.decision,
              );
              const isSaving = savingReview?.signalID === id;
              const evidence = Array.isArray(signal.evidence) ? signal.evidence : [];
              return (
                <article className="review-card" key={id}>
                  <header>
                    <div>
                      <span className="review-code">{signal.code}</span>
                      <h3>{signal.region}</h3>
                      <time dateTime={signal.window_start}>{formatWindow(signal.window_start)}</time>
                    </div>
                    <span className={currentOption ? `decision-chip ${currentOption.tone}` : "decision-chip pending"}>
                      {currentOption?.shortLabel ?? "Needs review"}
                    </span>
                  </header>
                  <dl className="review-evidence">
                    <div><dt>Story groups</dt><dd>{signal.stories}</dd></div>
                    <div><dt>Source domains</dt><dd>{signal.domains}</dd></div>
                    <div><dt>Prior baseline</dt><dd>{signal.baseline?.toFixed(1) ?? "—"}</dd></div>
                    <div><dt>Robust score</dt><dd>{formatSignalScore(signal)}</dd></div>
                  </dl>
                  <section className="source-evidence" aria-label={`Source evidence for ${signal.region}`}>
                    <div className="source-evidence-heading">
                      <div>
                        <span>Direct publisher evidence</span>
                        <strong>Source links by distinct story</strong>
                      </div>
                      <b>{evidence.length} {evidence.length === 1 ? "group" : "groups"}</b>
                    </div>
                    <p className="source-evidence-note">
                      GDELT tags are a starting point, not proof. Clear conflicts with a URL-derived headline are downgraded and cannot create an alert.
                    </p>
                    {evidence.length > 0 ? (
                      <ol className="evidence-story-list">
                        {evidence.map((story, storyIndex) => {
                          const publisherSources = (Array.isArray(story.sources) ? story.sources : [])
                            .filter((source) => safePublisherURL(source.url));
                          const primarySource = publisherSources[0];
                          return (
                            <li className="evidence-story" key={story.story_id}>
                              <div className="evidence-story-header">
                                <span>Story {String(storyIndex + 1).padStart(2, "0")}</span>
                                <small>{publisherSources.length} publisher {publisherSources.length === 1 ? "link" : "links"}</small>
                              </div>
                              {primarySource ? (
                                <a
                                  className="evidence-primary-link"
                                  href={safePublisherURL(primarySource.url) ?? undefined}
                                  rel="noopener noreferrer"
                                  target="_blank"
                                >
                                  {storyHeadline(story, primarySource)} <span aria-hidden="true">↗</span>
                                </a>
                              ) : (
                                <span className="evidence-primary-link unavailable">
                                  No safe publisher link retained
                                </span>
                              )}
                              <div className="evidence-context">
                                {story.location ? <span>{story.location}</span> : null}
                                {(story.themes ?? []).slice(0, 2).map((theme) => (
                                  <span key={theme}>{themeLabel(theme)}</span>
                                ))}
                              </div>
                              {publisherSources.length > 1 ? (
                                <details>
                                  <summary>Compare publisher versions</summary>
                                  <ul className="source-list">
                                    {publisherSources.map((source) => (
                                      <li key={source.url}>
                                        <a href={safePublisherURL(source.url) ?? undefined} rel="noopener noreferrer" target="_blank">
                                          <span>{source.domain}</span><b>Open ↗</b>
                                        </a>
                                      </li>
                                    ))}
                                  </ul>
                                </details>
                              ) : primarySource ? (
                                <p className="single-source">Source: {primarySource.domain}</p>
                              ) : null}
                            </li>
                          );
                        })}
                      </ol>
                    ) : (
                      <div className="source-evidence-empty">
                        <strong>No retained links for this window.</strong>
                        <span>Keep the signal uncertain unless you can verify it independently.</span>
                      </div>
                    )}
                  </section>
                  <p className="review-guardrail">
                    Choose “Real event” only when the news evidence appears to describe
                    a physical flood. This label does not issue a public warning.
                  </p>
                  <div className="review-actions" aria-label={`Review ${signal.region}`}>
                    {reviewOptions.map((option) => (
                      <button
                        className={`review-button ${option.tone}${currentReview?.decision === option.value ? " selected" : ""}`}
                        disabled={reviewConnection !== "ready" || isSaving || dataSource !== "api"}
                        key={option.value}
                        onClick={() => void saveReview(signal, option.value)}
                        type="button"
                        aria-pressed={currentReview?.decision === option.value}
                      >
                        {isSaving && savingReview?.decision === option.value ? "Saving…" : option.label}
                      </button>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="review-empty">
            <span aria-hidden="true">✓</span>
            <div>
              <strong>No candidate signals are waiting for review.</strong>
              <p>The queue will populate automatically when a reporting pattern passes every evidence gate.</p>
            </div>
          </div>
        )}

        <p className="review-storage">
          {reviewConnection === "ready"
            ? "Decisions are saved only on this PC in the local CrisisPulse review log."
            : reviewConnection === "loading"
              ? "Connecting to the local review log…"
              : "Start or restart the local API to save review decisions."}
        </p>
      </section>

      <section className="quality-section" aria-labelledby="quality-heading">
        <article className="quality-story">
          <p className="eyebrow">Evaluation readiness</p>
          <h2 id="quality-heading">Measure before you market.</h2>
          <p>
            Human labels reveal whether unusual news signals are useful. CrisisPulse
            waits for at least {reviewSummary?.minimum_sample ?? 20} resolved decisions
            before displaying any rate as a product-quality result.
          </p>
          <div className="quality-progress-copy">
            <strong>{reviewSummary?.resolved_reviews ?? 0} resolved labels</strong>
            <span>{reviewSummary?.minimum_sample ?? 20} minimum</span>
          </div>
          <span
            aria-label="Resolved review sample progress"
            aria-valuemax={reviewSummary?.minimum_sample ?? 20}
            aria-valuemin={0}
            aria-valuenow={reviewSummary?.resolved_reviews ?? 0}
            className="quality-progress-bar"
            role="progressbar"
          >
            <i style={{ width: `${sampleProgress}%` }} />
          </span>
          {reviewSummary?.status === "sample_ready" ? (
            <p className="quality-result ready">
              Reviewed event rate: <strong>{Math.round((reviewSummary.confirmed_event_rate ?? 0) * 100)}%</strong>
              <span>Irrelevant-news rate: {Math.round((reviewSummary.irrelevant_news_rate ?? 0) * 100)}%. Human review is not external disaster verification.</span>
            </p>
          ) : (
            <p className="quality-result">
              <strong>{reviewSummary?.remaining_to_sample ?? 20} more resolved decisions needed.</strong>
              <span>“Uncertain” labels stay in the dataset but do not count toward the minimum.</span>
            </p>
          )}
          {reviewConnection === "ready" ? (
            <a
              className="export-link"
              download="crisispulse-reviews.csv"
              href={reviewExportURL}
            >
              Download labels (.csv) <span aria-hidden="true">↓</span>
            </a>
          ) : (
            <span aria-disabled="true" className="export-link disabled">
              Download labels (.csv) <span aria-hidden="true">↓</span>
            </span>
          )}
        </article>

        <div className="quality-metrics" aria-label="Saved review totals">
          <article>
            <span>All labels</span>
            <strong>{formatNumber(reviewSummary?.total_reviews ?? 0)}</strong>
            <small>Latest decision per signal</small>
          </article>
          <article className="confirmed">
            <span>Real events</span>
            <strong>{formatNumber(reviewSummary?.confirmed_events ?? 0)}</strong>
            <small>Human-confirmed candidates</small>
          </article>
          <article className="irrelevant">
            <span>Irrelevant news</span>
            <strong>{formatNumber(reviewSummary?.irrelevant_news ?? 0)}</strong>
            <small>Observed false signals</small>
          </article>
          <article className="uncertain">
            <span>Uncertain</span>
            <strong>{formatNumber(reviewSummary?.uncertain ?? 0)}</strong>
            <small>Needs stronger evidence</small>
          </article>
        </div>
      </section>

      <section className="forecast-section" id="forecast" aria-labelledby="forecast-heading">
        <div className="forecast-heading">
          <div>
            <p className="eyebrow">Forecast lab</p>
            <h2 id="forecast-heading">Will reporting spread in the next six hours?</h2>
            <p>{forecast.target.definition}</p>
          </div>
          <span className={forecast.pending_predictions.length > 0 ? "forecast-status pending" : "forecast-status"}>
            {forecast.pending_predictions.length > 0
              ? `${forecast.pending_predictions.length} outcomes pending`
              : "No forecasts pending"}
          </span>
        </div>

        <div className="forecast-summary-grid">
          <article>
            <span>Completed outcome windows</span>
            <strong>{formatNumber(forecast.eligible_windows)}</strong>
            <small>Available for chronological model work</small>
          </article>
          <article>
            <span>Media-spread outcomes</span>
            <strong>{formatNumber(forecast.positive_outcomes)}</strong>
            <small>{outcomeBaseRate === null ? "No completed outcomes" : `${(outcomeBaseRate * 100).toFixed(2)}% historical base rate`}</small>
          </article>
          <article>
            <span>Evaluation-ready alerts</span>
            <strong>{formatNumber(forecast.evaluated_predictions)}</strong>
            <small>Baseline complete plus six future hours</small>
          </article>
        </div>

        {forecast.model.status === "ready" ? (
          <section className="model-benchmark" aria-label="First chronological model benchmark">
            <div className="model-benchmark-intro">
              <p className="eyebrow">First chronological model</p>
              <h3>Measured on later holdout hours.</h3>
              <p>
                The alert threshold was chosen on an earlier validation period, then
                reported on a later {forecast.model.test_hours}-hour holdout that was
                not used for fitting or threshold selection. This is an exploratory
                benchmark—not production validation.
              </p>
              <span>{formatNumber(forecast.model.test_rows)} holdout rows · {formatNumber(forecast.model.test_positives)} positive outcomes</span>
            </div>
            <div className="model-metrics">
              <article>
                <span>Ranking quality</span>
                <strong>{forecast.model.test_metrics.average_precision === null || forecast.model.test_metrics.average_precision === undefined ? "—" : `${(forecast.model.test_metrics.average_precision * 100).toFixed(1)}%`}</strong>
                <small>Average precision</small>
              </article>
              <article>
                <span>Alert precision</span>
                <strong>{forecast.model.test_metrics.precision === null || forecast.model.test_metrics.precision === undefined ? "—" : `${(forecast.model.test_metrics.precision * 100).toFixed(1)}%`}</strong>
                <small>Share of model alerts that spread</small>
              </article>
              <article>
                <span>Outcome recall</span>
                <strong>{forecast.model.test_metrics.recall === null || forecast.model.test_metrics.recall === undefined ? "—" : `${(forecast.model.test_metrics.recall * 100).toFixed(1)}%`}</strong>
                <small>Share of spread outcomes found</small>
              </article>
              <article>
                <span>False alerts / day</span>
                <strong>{forecast.model.test_metrics.false_alerts_per_day === null || forecast.model.test_metrics.false_alerts_per_day === undefined ? "—" : forecast.model.test_metrics.false_alerts_per_day.toFixed(1)}</strong>
                <small>Observed in the later holdout</small>
              </article>
            </div>
          </section>
        ) : (
          <div className="model-unavailable">
            <strong>First chronological benchmark pending.</strong>
            <span>It will appear after the local outcome and model refresh completes.</span>
          </div>
        )}

        <div className="forecast-workbench">
          <div className="pending-forecast-list">
            <div className="forecast-subheading">
              <strong>Open forecast clocks</strong>
              <span>Future data stays hidden until maturity</span>
            </div>
            {forecast.pending_predictions.length > 0 ? (
              forecast.pending_predictions.map((prediction) => {
                const hoursObserved = Math.max(
                  0,
                  forecast.target.horizon_hours - prediction.hours_remaining,
                );
                const modelPrediction = modelPredictions.get(
                  `${prediction.region_code}|${prediction.window_start}`,
                );
                return (
                  <article className="pending-forecast" key={`${prediction.region_code}|${prediction.window_start}`}>
                    <div className="pending-forecast-title">
                      <div>
                        <span>{prediction.region_code}</span>
                        <strong>{formatWindow(prediction.window_start)}</strong>
                      </div>
                      <b>{prediction.hours_remaining}h remaining</b>
                    </div>
                    <dl>
                      <div><dt>At detection</dt><dd>{prediction.stories_at_detection} stories</dd></div>
                      <div><dt>Source diversity</dt><dd>{prediction.domains_at_detection} domains</dd></div>
                      <div><dt>Outcome closes</dt><dd>{formatWindow(prediction.matures_at)}</dd></div>
                    </dl>
                    {modelPrediction ? (
                      <div className="pending-model-score">
                        <span>Model score</span>
                        <strong>{(modelPrediction.model_score * 100).toFixed(1)} / 100</strong>
                        <small>
                          {modelPrediction.clears_alert_threshold
                            ? "Clears the conservative alert threshold"
                            : forecast.model.decision_threshold === null
                              ? "Does not clear the alert threshold"
                              : `Below the conservative ${(forecast.model.decision_threshold * 100).toFixed(2)} / 100 threshold`}
                        </small>
                        <em>Ranking score—not a calibrated probability.</em>
                      </div>
                    ) : null}
                    <span
                      aria-label={`${hoursObserved} of ${forecast.target.horizon_hours} outcome hours observed`}
                      aria-valuemax={forecast.target.horizon_hours}
                      aria-valuemin={0}
                      aria-valuenow={hoursObserved}
                      className="forecast-clock"
                      role="progressbar"
                    >
                      <i style={{ width: `${(hoursObserved / forecast.target.horizon_hours) * 100}%` }} />
                    </span>
                  </article>
                );
              })
            ) : (
              <div className="forecast-empty">No candidate forecasts are waiting for future data.</div>
            )}
          </div>

          <aside className="evaluation-gate">
            <span>Evaluation gate</span>
            {forecast.evaluation_ready_windows === 0 ? (
              <>
                <strong>Waiting by design</strong>
                <p>
                  The detector needs 168 prior hours, then each prediction needs six
                  untouched future hours. Those two windows do not overlap yet.
                </p>
              </>
            ) : (
              <>
                <strong>{formatNumber(forecast.evaluation_ready_windows)} windows ready</strong>
                <p>
                  Precision: {forecast.precision === null ? "—" : `${Math.round(forecast.precision * 100)}%`} · Recall: {forecast.recall === null ? "—" : `${Math.round(forecast.recall * 100)}%`}
                </p>
              </>
            )}
            <dl>
              <div><dt>Prediction time</dt><dd>Hour 0 features only</dd></div>
              <div><dt>Outcome window</dt><dd>Hours 1–{forecast.target.horizon_hours}</dd></div>
              <div><dt>Success threshold</dt><dd>{forecast.target.domain_threshold} domains</dd></div>
            </dl>
          </aside>
        </div>
      </section>

      <section className="content-grid" id="signals">
        <article className="surface evidence-surface">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Latest eligible hour</p>
              <h2>Signals with enough evidence</h2>
            </div>
            <span className={hasCandidates ? "status-badge alert" : "status-badge"}>
              {hasCandidates
                ? `${snapshot.candidates} ${snapshot.candidates === 1 ? "candidate" : "candidates"}`
                : `${statusCounts.normal} normal`}
            </span>
          </div>

          <div className="table-wrap">
            <table className="signal-table">
              <thead>
                <tr>
                  <th scope="col">Region</th>
                  <th scope="col">Stories</th>
                  <th scope="col">Domains</th>
                  <th scope="col">Baseline</th>
                  <th scope="col">Score</th>
                  <th scope="col">Signal status</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((signal) => (
                  <tr key={signalID(signal)}>
                    <td data-label="Region"><strong>{signal.region}</strong><small>{signal.code}</small></td>
                    <td data-label="Stories">{signal.stories}</td>
                    <td data-label="Domains">{signal.domains}</td>
                    <td data-label="Baseline">{signal.baseline?.toFixed(1) ?? "—"}</td>
                    <td className="mono" data-label="Score">{formatSignalScore(signal)}</td>
                    <td data-label="Signal status">
                      <span className={signal.status === "candidate_anomaly" ? "alert-pill" : "normal-pill"}>
                        <i />{signal.status_label}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="table-note">
            “Normal” means reporting was not unusually high compared with the
            prior seven days. It is not a statement about physical flood conditions.
          </p>
        </article>

        <aside className="surface readiness-surface">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Scoring readiness</p>
              <h2>What happened to every row</h2>
            </div>
          </div>
          <div className="status-list">
            {statusRows.map((row) => {
              const count = statusCounts[row.key];
              return (
                <div key={row.key}>
                  <span className="status-name"><i className={`dot ${row.tone}`} />{row.label}</span>
                  <strong>{formatNumber(count)}</strong>
                  <span className="status-bar"><i style={{ width: barWidth(count) }} /></span>
                </div>
              );
            })}
          </div>
          <div className="next-window">
            <span>Human review active</span>
            <strong>Turn candidates into labeled evidence</strong>
            <p>Saved decisions create the foundation for measuring false positives and improving alert quality.</p>
          </div>
        </aside>
      </section>

      <section className="method-strip" id="method" aria-label="How CrisisPulse works">
        <div>
          <p className="eyebrow">How this result was made</p>
          <h2>News evidence in. Explainable decisions out.</h2>
        </div>
        <ol>
          <li><span>01</span><strong>Collect</strong><small>15-minute GDELT updates</small></li>
          <li><span>02</span><strong>Clean</strong><small>Remove repeats and weak matches</small></li>
          <li><span>03</span><strong>Group</strong><small>Region, hour, and story</small></li>
          <li><span>04</span><strong>Compare</strong><small>Prior-hour median and spread</small></li>
          <li><span>05</span><strong>Gate</strong><small>Require history and source diversity</small></li>
        </ol>
      </section>

      <footer>
        <p><strong>CrisisPulse</strong> detects unusual disaster-related news reporting. It is not an emergency warning system.</p>
        <p>Local portfolio MVP · GDELT public data · $0 API cost</p>
      </footer>
    </main>
  );
}
