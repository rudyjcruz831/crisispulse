"use client";

import { useEffect, useState } from "react";
import bundledDashboardData from "../data/dashboard.json";

type DashboardData = typeof bundledDashboardData;

const snapshotURL = "http://127.0.0.1:8080/api/v1/snapshot";

const formatNumber = (value: number) => value.toLocaleString("en-US");
const formatScore = (value: number | null) => {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`.replace("-", "−");
};

const statusRows = [
  { key: "insufficient_history", label: "Building history", tone: "waiting" },
  { key: "below_minimum_support", label: "Below evidence minimum", tone: "quiet" },
  { key: "normal", label: "Normal", tone: "normal" },
  { key: "candidate_anomaly", label: "Candidate anomaly", tone: "alert" },
] as const;

export default function Home() {
  const [dashboardData, setDashboardData] = useState<DashboardData>(bundledDashboardData);
  const [dataSource, setDataSource] = useState<"api" | "snapshot">("snapshot");
  const { snapshot, signals, parameters, status_counts: statusCounts } = dashboardData;
  const hasCandidates = snapshot.candidates > 0;
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
                  <th scope="col">Decision</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((signal) => (
                  <tr key={signal.code}>
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
            <span>Next milestone</span>
            <strong>Accumulate more eligible hours</strong>
            <p>More history lets us measure whether alert candidates remain stable over time.</p>
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
