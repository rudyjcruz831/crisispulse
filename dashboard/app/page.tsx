"use client";

import { useEffect, useState } from "react";
import bundledDashboardData from "../data/dashboard.json";

type EvidenceSource = { domain: string; url: string };
type EvidenceStory = {
  story_id: string;
  seen_at: string;
  location: string | null;
  themes: string[];
  sources: EvidenceSource[];
};
type BundledSignal = (typeof bundledDashboardData)["signals"][number];
type Signal = Omit<BundledSignal, "evidence"> & { evidence: EvidenceStory[] };
type DashboardData = Omit<typeof bundledDashboardData, "signals"> & { signals: Signal[] };
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

const snapshotURL = "/api/v1/snapshot";
const reviewsURL = "/api/v1/reviews";

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
const sourceLabel = (source: EvidenceSource) => {
  try {
    const parsed = new URL(source.url);
    const finalSegment = parsed.pathname.split("/").filter(Boolean).at(-1);
    if (!finalSegment) return source.domain;
    const readable = decodeURIComponent(finalSegment)
      .replace(/[-_]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!readable) return source.domain;
    return readable.replace(/\b\w/g, (letter) => letter.toUpperCase());
  } catch {
    return source.domain;
  }
};
const themeLabel = (theme: string) => {
  const readable = theme
    .replace(/^NATURAL_DISASTER_/, "")
    .replaceAll("_", " ")
    .toLowerCase();
  return readable.charAt(0).toUpperCase() + readable.slice(1);
};
const signalID = (signal: Signal) => `${signal.code}|${signal.window_start}`;
const formatWindow = (value: string) => {
  const date = new Date(value.endsWith("Z") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC",
  })} UTC`;
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
  const [reviewConnection, setReviewConnection] = useState<"loading" | "ready" | "unavailable">("loading");
  const [savingReview, setSavingReview] = useState<{ signalID: string; decision: ReviewDecision } | null>(null);
  const [reviewNotice, setReviewNotice] = useState<string | null>(null);
  const { snapshot, signals, parameters, status_counts: statusCounts } = dashboardData;
  const hasCandidates = snapshot.candidates > 0;
  const candidateSignals = signals.filter((signal) => signal.status === "candidate_anomaly");
  const reviewedCount = candidateSignals.filter((signal) => reviews[signalID(signal)]).length;
  const barWidth = (count: number) =>
    count === 0 ? "0%" : `${Math.max(3, (count / snapshot.scored_rows) * 100)}%`;

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
        setDashboardData(nextData);
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
    fetch(reviewsURL, { cache: "no-store", signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Review API returned ${response.status}`);
        return response.json() as Promise<ReviewsResponse>;
      })
      .then((payload) => {
        const latest = Object.fromEntries(
          payload.reviews.map((review) => [review.signal_id, review]),
        );
        setReviews(latest);
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
        <div className="header-meta">
          <span className={dataSource === "api" ? "live-dot" : "live-dot snapshot"} aria-hidden="true" />
          {dataSource === "api" ? "Live API connected" : "Verified local snapshot"}
          <strong>{snapshot.updated_label}</strong>
        </div>
      </header>

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
            <div><dt>Alert threshold</dt><dd>Robust z ≥ {parameters.z_threshold.toFixed(1)}</dd></div>
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

      <section className="review-section" aria-labelledby="review-heading">
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
              const evidence = signal.evidence ?? [];
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
                    <div><dt>Robust score</dt><dd>{formatScore(signal.score)}</dd></div>
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
                      GDELT supplies publisher URLs rather than verified headlines. Link labels below are derived from each URL path.
                    </p>
                    {evidence.length > 0 ? (
                      <ol className="evidence-story-list">
                        {evidence.map((story, storyIndex) => {
                          const primarySource = story.sources[0];
                          return (
                            <li className="evidence-story" key={story.story_id}>
                              <div className="evidence-story-header">
                                <span>Story {String(storyIndex + 1).padStart(2, "0")}</span>
                                <small>{story.sources.length} publisher {story.sources.length === 1 ? "link" : "links"}</small>
                              </div>
                              <a
                                className="evidence-primary-link"
                                href={primarySource.url}
                                rel="noopener noreferrer"
                                target="_blank"
                              >
                                {sourceLabel(primarySource)} <span aria-hidden="true">↗</span>
                              </a>
                              <div className="evidence-context">
                                {story.location ? <span>{story.location}</span> : null}
                                {story.themes.slice(0, 2).map((theme) => (
                                  <span key={theme}>{themeLabel(theme)}</span>
                                ))}
                              </div>
                              {story.sources.length > 1 ? (
                                <details>
                                  <summary>Compare publisher versions</summary>
                                  <ul className="source-list">
                                    {story.sources.map((source) => (
                                      <li key={source.url}>
                                        <a href={source.url} rel="noopener noreferrer" target="_blank">
                                          <span>{source.domain}</span><b>Open ↗</b>
                                        </a>
                                      </li>
                                    ))}
                                  </ul>
                                </details>
                              ) : (
                                <p className="single-source">Source: {primarySource.domain}</p>
                              )}
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

      <section className="content-grid">
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
            <table>
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
                    <td><strong>{signal.region}</strong><small>{signal.code}</small></td>
                    <td>{signal.stories}</td>
                    <td>{signal.domains}</td>
                    <td>{signal.baseline?.toFixed(1) ?? "—"}</td>
                    <td className="mono">{formatScore(signal.score)}</td>
                    <td>
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

      <section className="method-strip" aria-label="How CrisisPulse works">
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
