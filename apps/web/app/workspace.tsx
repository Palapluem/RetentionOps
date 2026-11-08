"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useRef, useState } from "react";
import {
  type Cohort,
  type Customer,
  type JobPage,
  number,
  percent,
  type Risk,
  readData,
  shortDate,
  timestamp,
  type WorkspaceData,
} from "../lib/data";

export type View = "system" | "overview" | "risk" | "cohorts" | "status";
const views: { id: View; label: string; description: string }[] = [
  {
    id: "system",
    label: "System dashboard",
    description: "Follow the local pipeline, verify the active release and check source readiness.",
  },
  {
    id: "overview",
    label: "Overview",
    description: "A clear view of subscriber risk and cohort outcomes.",
  },
  {
    id: "risk",
    label: "Risk explorer",
    description: "Find subscribers to review and inspect the observations behind each score.",
  },
  {
    id: "cohorts",
    label: "Cohort analytics",
    description: "Compare observed renewal outcomes across mature subscription cohorts.",
  },
  {
    id: "status",
    label: "Data & model",
    description: "Trace the published results to their source, model and pipeline run.",
  },
];
const bandName = { high: "High", watch: "Watch", low: "Lower" };
const runNames: Record<string, string> = {
  events: "Event pipeline",
  snapshots: "Snapshot pipeline",
  "event-source": "Source replay",
  "source-generation": "Source generation",
  "source-intake": "Source intake",
};
const featureNames: Record<string, string> = {
  active_days_30d: "Active days in 30 days",
  payment_failures_90d: "Failed payments in 90 days",
  tenure_months: "Tenure in 30-day months",
  monthly_fee: "Monthly fee (simulated units)",
  auto_renew: "Auto-renew enabled",
};
type Filters = { search: string; band: string; auto: string };
const emptyFilters: Filters = { search: "", band: "all", auto: "all" };
const pageSize = 12;

function riskLocation(params: { get: (name: string) => string | null }) {
  const search = params.get("search")?.trim() || "";
  const band = params.get("band");
  const auto = params.get("auto_renew");
  const requestedPage = Number(params.get("page") || "1");
  const page =
    Number.isSafeInteger(requestedPage) &&
    requestedPage >= 1 &&
    requestedPage <= Math.floor(100000 / pageSize) + 1
      ? requestedPage
      : 1;
  return {
    filters: {
      search: /^[A-Za-z0-9-]{0,32}$/.test(search) ? search : "",
      band: band && ["high", "watch", "low"].includes(band) ? band : "all",
      auto: auto === "0" || auto === "1" ? auto : "all",
    },
    offset: (page - 1) * pageSize,
  };
}

function riskHref(filters: Filters, offset: number) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.band !== "all") params.set("band", filters.band);
  if (filters.auto !== "all") params.set("auto_renew", filters.auto);
  if (offset > 0) params.set("page", String(Math.floor(offset / pageSize) + 1));
  const query = params.toString();
  return query ? `/risk?${query}` : "/risk";
}

function RiskFiltersForm({
  applied,
  apply,
  clear,
}: {
  applied: Filters;
  apply: (filters: Filters) => void;
  clear: () => void;
}) {
  const [filters, setFilters] = useState<Filters>(applied);
  return (
    <form
      className="filters"
      onSubmit={(event) => {
        event.preventDefault();
        apply({ ...filters, search: filters.search.trim() });
      }}
    >
      <label htmlFor="search">
        Subscriber ID
        <input
          id="search"
          name="search"
          type="search"
          autoComplete="off"
          placeholder="Search SYN-00001"
          pattern="[A-Za-z0-9-]*"
          title="Use letters, digits and hyphens."
          maxLength={32}
          value={filters.search}
          onChange={(event) => setFilters({ ...filters, search: event.target.value })}
        />
      </label>
      <label htmlFor="band">
        Risk band
        <select
          id="band"
          name="band"
          value={filters.band}
          onChange={(event) => setFilters({ ...filters, band: event.target.value })}
        >
          <option value="all">All risk bands</option>
          <option value="high">High</option>
          <option value="watch">Watch</option>
          <option value="low">Lower</option>
        </select>
      </label>
      <label htmlFor="renewal">
        Auto-renew
        <select
          id="renewal"
          name="auto_renew"
          value={filters.auto}
          onChange={(event) => setFilters({ ...filters, auto: event.target.value })}
        >
          <option value="all">All renewal settings</option>
          <option value="1">On</option>
          <option value="0">Off</option>
        </select>
      </label>
      <button type="submit" className="button primary">
        Apply filters
      </button>
      <button
        type="button"
        className="button secondary"
        onClick={() => {
          setFilters(emptyFilters);
          clear();
        }}
      >
        Clear
      </button>
    </form>
  );
}

export function Frame({
  view,
  children,
  refresh,
  cutoff,
}: {
  view: View;
  children: ReactNode;
  refresh: () => void;
  cutoff?: string;
}) {
  const selected = views.find((v) => v.id === view) ?? views[0];
  return (
    <div className="app-shell">
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <aside className="sidebar">
        <Link href="/" className="brand">
          <span className="brand-mark" aria-hidden="true">
            R
          </span>
          <span>
            RetentionOps<small>Subscriber intelligence</small>
          </span>
        </Link>
        <nav aria-label="Main navigation">
          {views.map((v) => (
            <Link
              key={v.id}
              href={v.id === "system" ? "/" : `/${v.id}`}
              className={view === v.id ? "nav-item active" : "nav-item"}
              aria-current={view === v.id ? "page" : undefined}
            >
              {v.label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="source-dot" aria-hidden="true" />
          Synthetic subscriptions
          <p>
            Historical analysis.
            <br />
            No live customer data.
          </p>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>Retention intelligence / {selected.label}</span>
          <button type="button" className="button secondary" onClick={refresh}>
            Refresh view
          </button>
        </header>
        <main id="content">
          <div className="page-heading">
            <div>
              <h1>{selected.label}</h1>
              <p>{selected.description}</p>
            </div>
            <span className="badge synthetic">Synthetic data</span>
          </div>
          <div className="provenance">
            <span aria-hidden="true">◷</span>
            <span>
              {cutoff
                ? `Historical prediction cutoff: ${shortDate(cutoff)}. `
                : "Historical synthetic analysis. "}
              Scores are simulated; they do not measure campaign effectiveness.
            </span>
          </div>
          {children}
        </main>
        <footer>
          RetentionOps · Synthetic historical workspace
          <span>Risk is predictive, not a causal campaign effect.</span>
        </footer>
      </div>
    </div>
  );
}

function Metrics({ data }: { data: WorkspaceData }) {
  const m = data.overview;
  return (
    <dl className="metric-strip">
      <div>
        <dt>Scored subscribers</dt>
        <dd>
          <span className="metric-value">{number(m.customers)}</span>
          <small>Cutoff {shortDate(m.score_cutoff)}</small>
        </dd>
      </div>
      <div>
        <dt>High-risk subscribers</dt>
        <dd>
          <span className="metric-value">{number(m.high_risk_customers)}</span>
          <small>Probability of at least 40%</small>
        </dd>
      </div>
      <div>
        <dt>Average predicted risk</dt>
        <dd>
          <span className="metric-value">{percent(m.mean_predicted_risk)}</span>
          <small>Across the scored cohort</small>
        </dd>
      </div>
      <div>
        <dt>Review capacity at 10%</dt>
        <dd>
          <span className="metric-value">{number(m.review_capacity)}</span>
          <small>Ranking threshold for evaluation</small>
        </dd>
      </div>
    </dl>
  );
}

function CohortTrend({ items }: { items: Cohort[] }) {
  const [index, setIndex] = useState(items.length - 1);
  const selected = items[index] || items[items.length - 1];
  if (!selected) return <p>No mature cohort observations are available.</p>;
  const max = Math.max(0.1, ...items.map((c) => c.churn_rate));
  return (
    <div className="cohort-visual">
      <div className="chart-summary">
        <div>
          <span className="muted">{shortDate(selected.as_of_date)}</span>
          <strong>{percent(selected.churn_rate)}</strong>
        </div>
        <p>
          {number(selected.churned)} churned / {number(selected.eligible)} eligible
          <br />
          <span className="muted">Observed churn after the 30-day renewal window</span>
        </p>
      </div>
      <section className="cohort-chart" aria-label="Observed churn by mature cohort">
        {items.map((c, i) => (
          <button
            type="button"
            key={c.as_of_date}
            className={i === index ? "cohort-column selected" : "cohort-column"}
            aria-pressed={i === index}
            onClick={() => setIndex(i)}
          >
            <span className="bar-label">{percent(c.churn_rate)}</span>
            <span className="chart-track" aria-hidden="true">
              <span
                className="chart-fill"
                style={{ height: `${Math.max(2, (c.churn_rate / max) * 100)}%` }}
              />
            </span>
            <span>{shortDate(c.as_of_date).split(" ").slice(1, 2).join("")}</span>
            <small>{c.partition}</small>
            <span className="visually-hidden">{shortDate(c.as_of_date)}: observed churn</span>
          </button>
        ))}
      </section>
      <p className="caption">
        Each bar uses its own mature eligible cohort. Training and validation outcomes are shown for
        context.
      </p>
    </div>
  );
}

function ScrollArea({ label, children }: { label: string; children: ReactNode }) {
  return (
    // biome-ignore lint/a11y/noNoninteractiveTabindex: Overflowing tables require a keyboard focus target, verified by browser tests.
    <section className="table-scroll" tabIndex={0} aria-label={label}>
      {children}
    </section>
  );
}

function RiskTable({ items, open }: { items: Risk[]; open: (row: Risk) => void }) {
  return (
    <ScrollArea label="Ranked subscriber table">
      <table>
        <thead>
          <tr>
            <th scope="col">Subscriber</th>
            <th scope="col">Churn probability</th>
            <th scope="col">Risk band</th>
            <th scope="col">Active days / 30</th>
            <th scope="col">Failed payments / 90d</th>
            <th scope="col">Auto-renew</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr key={row.customer_id}>
              <td>
                <button type="button" className="customer-link" onClick={() => open(row)}>
                  {row.customer_id}
                </button>
              </td>
              <td>
                <div className="probability">
                  <strong>{percent(row.churn_probability)}</strong>
                  <span className="prob-track" aria-hidden="true">
                    <span style={{ width: `${row.churn_probability * 100}%` }} />
                  </span>
                </div>
              </td>
              <td>
                <span className={`badge ${row.risk_band}`}>{bandName[row.risk_band]}</span>
              </td>
              <td>{row.active_days_30d}</td>
              <td>{row.payment_failures_90d}</td>
              <td>{row.auto_renew ? "On" : "Off"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollArea>
  );
}

function Evaluation({ data }: { data: WorkspaceData }) {
  const m = data.overview;
  return (
    <section className="panel evaluation">
      <div className="section-heading">
        <h2>Holdout evaluation</h2>
        <span className="subtle-label">
          {data.status.model_family === "lightgbm" ? "LightGBM" : "Logistic Regression"}
        </span>
      </div>
      <dl className="evaluation-grid">
        <div>
          <dt>Average precision</dt>
          <dd>
            <span className="metric-value">{m.average_precision.toFixed(3)}</span>
            <small>Constant baseline {m.baseline_average_precision.toFixed(3)}</small>
          </dd>
        </div>
        <div>
          <dt>Recall at top 10%</dt>
          <dd>
            <span className="metric-value">{percent(m.recall_at_10pct)}</span>
            <small>Share of observed churners captured</small>
          </dd>
        </div>
        <div>
          <dt>Brier score</dt>
          <dd>
            <span className="metric-value">{m.brier.toFixed(3)}</span>
            <small>Lower is better</small>
          </dd>
        </div>
        <div>
          <dt>ROC-AUC</dt>
          <dd>
            <span className="metric-value">{m.roc_auc.toFixed(3)}</span>
            <small>Ranking discrimination</small>
          </dd>
        </div>
      </dl>
      <p className="caption">
        Evaluated on the historical September test cohort. Synthetic performance is not evidence of
        real customer prediction quality.
      </p>
    </section>
  );
}

function CohortsView({ data }: { data: WorkspaceData }) {
  return (
    <>
      <section className="panel">
        <div className="section-heading">
          <h2>Observed renewal outcomes</h2>
          <span className="subtle-label">Label freeze {shortDate(data.cohorts.label_freeze)}</span>
        </div>
        <CohortTrend items={data.cohorts.items} />
      </section>
      <section className="panel">
        <div className="section-heading">
          <h2>Cohort breakdown</h2>
          <span className="muted">Denominator: eligible subscription opportunities</span>
        </div>
        <ScrollArea label="Cohort breakdown">
          <table>
            <thead>
              <tr>
                <th scope="col">Cutoff</th>
                <th scope="col">Partition</th>
                <th scope="col">Eligible</th>
                <th scope="col">Churned</th>
                <th scope="col">Observed churn</th>
                <th scope="col">Avg. active days</th>
                <th scope="col">Auto-renew share</th>
              </tr>
            </thead>
            <tbody>
              {data.cohorts.items.map((c) => (
                <tr key={c.as_of_date}>
                  <td>{shortDate(c.as_of_date)}</td>
                  <td>
                    <span className="badge neutral">{c.partition}</span>
                  </td>
                  <td>{number(c.eligible)}</td>
                  <td>{number(c.churned)}</td>
                  <td>{percent(c.churn_rate)}</td>
                  <td>{c.mean_active_days.toFixed(1)}</td>
                  <td>{percent(c.auto_renew_share)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollArea>
        <p className="caption">
          Synthetic monthly opportunities can include reactivation. These are not survival-retention
          cohorts of a fixed signup population.
        </p>
      </section>
    </>
  );
}

function StatusView({ data }: { data: WorkspaceData }) {
  const s = data.status;
  return (
    <>
      <div className="two-column">
        <section className="panel">
          <h2>Published data</h2>
          <dl className="lineage">
            <dt>Feature origin</dt>
            <dd>{s.feature_origin}</dd>
            <dt>Source coverage</dt>
            <dd>
              {s.source_complete_through
                ? shortDate(s.source_complete_through)
                : "Snapshot source; event coverage unavailable"}
            </dd>
            <dt>Evaluation freeze</dt>
            <dd>{shortDate(s.evaluation_freeze)}</dd>
            <dt>Eligible feature rows</dt>
            <dd>{number(data.cohorts.items.reduce((sum, c) => sum + c.eligible, 0))}</dd>
            <dt>Input event revisions</dt>
            <dd>
              {s.quality.input_event_revisions !== undefined
                ? number(Number(s.quality.input_event_revisions))
                : "Not available for snapshot source"}
            </dd>
            <dt>Excluded unknown subscriptions</dt>
            <dd>{s.quality.excluded_no_known_subscription ?? "Not available"}</dd>
          </dl>
        </section>
        <section className="panel">
          <h2>Model release</h2>
          <dl className="lineage">
            <dt>Estimator</dt>
            <dd>{s.model_family === "lightgbm" ? "LightGBM" : "Logistic Regression"}</dd>
            <dt>Selected candidate</dt>
            <dd>{s.selected_candidate}</dd>
            <dt>Validation average precision</dt>
            <dd>{s.validation_average_precision?.toFixed(3) ?? "Legacy fixed baseline"}</dd>
            <dt>Trained</dt>
            <dd>{timestamp(s.trained_at)}</dd>
            <dt>Scored cohort</dt>
            <dd>
              {shortDate(data.overview.score_cutoff)} · {number(data.overview.customers)}{" "}
              subscribers
            </dd>
            <dt>Model inputs</dt>
            <dd>{s.features.map((f) => featureNames[f] || f).join(", ")}</dd>
          </dl>
          <details className="hash-details">
            <summary>Source and artifact identifiers</summary>
            <dl className="lineage">
              <dt>Model version</dt>
              <dd>
                <code>{s.model_version}</code>
              </dd>
              <dt>Event release</dt>
              <dd>
                <code>{s.event_release_id || "No event source"}</code>
              </dd>
              <dt>Snapshot release</dt>
              <dd>
                <code>{s.source_release_id}</code>
              </dd>
              <dt>Dataset SHA-256</dt>
              <dd>
                <code>{s.dataset_sha256}</code>
              </dd>
              <dt>Model SHA-256</dt>
              <dd>
                <code>{s.model_sha256}</code>
              </dd>
            </dl>
          </details>
        </section>
      </div>
      <section className="panel">
        <div className="section-heading">
          <h2>Recent pipeline runs</h2>
          <span className="subtle-label">Actual local job attempts</span>
        </div>
        <RunHistoryTable
          runs={s.runs}
          label="Pipeline run history"
          emptyMessage="No pipeline run history has been recorded for this publication."
        />
        <p className="caption">
          A failed attempt preserves the last successful publication. Job completion time and
          historical data cutoff describe different kinds of freshness.
        </p>
      </section>
      <section className="panel limitations">
        <h2>Interpretation and limits</h2>
        <ul>
          {s.limitations.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      </section>
    </>
  );
}

export function RunHistoryTable({
  runs,
  label,
  emptyMessage,
}: {
  runs: JobPage["items"];
  label: string;
  emptyMessage: string;
}) {
  if (!runs.length) return <p>{emptyMessage}</p>;
  return (
    <>
      <ScrollArea label={label}>
        <table>
          <thead>
            <tr>
              <th scope="col">Started</th>
              <th scope="col">Pipeline</th>
              <th scope="col">State</th>
              <th scope="col">Output rows</th>
              <th scope="col">Duration</th>
              <th scope="col">Error type</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.run_id}>
                <td>{timestamp(run.started_at)}</td>
                <td>{runNames[run.mode] || run.mode}</td>
                <td>
                  <span
                    className={`badge ${run.state === "succeeded" ? "low" : run.state === "failed" ? "high" : "watch"}`}
                  >
                    {run.state === "running" ? "running (last recorded)" : run.state}
                  </span>
                </td>
                <td>{run.output_rows === null ? "—" : number(run.output_rows)}</td>
                <td>
                  {run.elapsed_seconds === null
                    ? "Not recorded"
                    : `${run.elapsed_seconds.toFixed(2)}s`}
                </td>
                <td>{run.error_type || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollArea>
      {runs.some((run) => run.state === "running") && (
        <p className="caption">
          A running state is the last recorded state; it does not confirm that the process is still
          active. Check the process before retrying.
        </p>
      )}
    </>
  );
}

type DetailState =
  | { kind: "loading"; id: string }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: Customer }
  | null;

export default function Workspace({ view }: { view: View }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { filters: applied, offset } = riskLocation(searchParams);
  const [refresh, setRefresh] = useState(0);
  const [result, setResult] = useState<{
    key: string;
    data?: WorkspaceData;
    error?: string;
    jobs?: JobPage;
  } | null>(null);
  const [detail, setDetail] = useState<DetailState>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const detailRequest = useRef<AbortController | null>(null);
  const query = new URLSearchParams({
    limit: String(pageSize),
    offset: String(view === "risk" ? offset : 0),
  });
  if (view === "risk") {
    if (applied.search) query.set("search", applied.search);
    query.set("band", applied.band);
    if (applied.auto !== "all") query.set("auto_renew", applied.auto);
  }
  const path = `workspace?${query.toString()}`;
  const key = `${path}|${refresh}`;
  useEffect(() => {
    const controller = new AbortController();
    readData<WorkspaceData>(path, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setResult({ key, data });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof Error ? error.message : "Published results are unavailable.";
        setResult({ key, error: message });
        readData<JobPage>("jobs", controller.signal)
          .then((jobs) => {
            if (!controller.signal.aborted) setResult({ key, error: message, jobs });
          })
          .catch(() => {
            // Keep the primary workspace error visible when independent history is also unavailable.
          });
      });
    return () => controller.abort();
  }, [path, key]);
  useEffect(() => () => detailRequest.current?.abort(), []);
  const reload = () => setRefresh((current) => current + 1);
  const current = result?.key === key ? result : null;
  const data = current?.data;
  if (!current)
    return (
      <Frame view={view} refresh={reload}>
        <section className="state-panel" role="status" aria-live="polite">
          <div className="loading-bars" aria-hidden="true">
            <i />
            <i />
            <i />
          </div>
          <h2>Loading published results</h2>
          <p>Checking the active data and model publication.</p>
        </section>
      </Frame>
    );
  if (!data)
    return (
      <Frame view={view} refresh={reload}>
        <section className="state-panel error-state" role="alert">
          <span className="badge high">Data unavailable</span>
          <h2>Results could not be loaded</h2>
          <p>{current.error}</p>
          <button type="button" className="button primary" onClick={reload}>
            Retry
          </button>
          <p className="caption">
            {current.jobs?.publication_present === false
              ? "No successful publication exists yet. Retry after a valid pipeline run completes."
              : current.jobs?.publication_present
                ? "The last successful publication remains active. Retry when the data service is available."
                : "Publication state could not be confirmed. Retry when the data service is available."}
          </p>
        </section>
        {current.jobs && (
          <section className="panel">
            <div className="section-heading">
              <h2>Latest pipeline attempts</h2>
              <span className="subtle-label">Actual local job history</span>
            </div>
            <RunHistoryTable
              runs={current.jobs.items}
              label="Latest pipeline attempts"
              emptyMessage="No pipeline attempt has been recorded."
            />
          </section>
        )}
      </Frame>
    );

  const displayedVersion = data.overview.model_version;
  async function openCustomer(row: Risk) {
    detailRequest.current?.abort();
    const request = new AbortController();
    detailRequest.current = request;
    setDetail({ kind: "loading", id: row.customer_id });
    dialog.current?.showModal();
    try {
      const customer = await readData<Customer>(
        `customers/${row.customer_id}?model_version=${displayedVersion}`,
        request.signal,
      );
      if (!request.signal.aborted && dialog.current?.open)
        setDetail({ kind: "ready", data: customer });
    } catch (error) {
      if (!request.signal.aborted)
        setDetail({
          kind: "error",
          message: error instanceof Error ? error.message : "Details are unavailable.",
        });
    }
  }
  function clear() {
    router.push("/risk", { scroll: false });
  }

  return (
    <Frame view={view} refresh={reload} cutoff={data.overview.score_cutoff}>
      {view === "overview" && (
        <>
          <Metrics data={data} />
          <div className="overview-grid">
            <section className="panel">
              <div className="section-heading">
                <h2>Cohort history</h2>
                <Link href="/cohorts" className="text-link">
                  Explore cohorts
                </Link>
              </div>
              <CohortTrend items={data.cohorts.items} />
            </section>
            <section className="review-note">
              <span className="badge neutral">Review guidance</span>
              <h2>
                Start with risk.
                <br />
                Review the context.
              </h2>
              <p>
                Use activity, payment history and renewal settings to prepare an informed subscriber
                review.
              </p>
              <dl>
                <dt>Observed test-cohort churn</dt>
                <dd>{percent(data.overview.observed_churn_rate)}</dd>
                <dt>Data mode</dt>
                <dd>
                  {data.status.event_release_id
                    ? "Synthetic subscription events"
                    : "Simulated snapshots"}
                </dd>
              </dl>
              <Link className="button primary" href="/risk">
                Open risk explorer
              </Link>
            </section>
          </div>
          <section className="panel">
            <div className="section-heading">
              <div>
                <h2>Highest-risk subscribers</h2>
                <p className="caption">
                  Top five in the scored cohort. Open a subscriber to inspect their features.
                </p>
              </div>
              <Link href="/risk" className="text-link">
                View full ranking
              </Link>
            </div>
            <RiskTable items={data.risk.items.slice(0, 5)} open={openCustomer} />
          </section>
          <Evaluation data={data} />
        </>
      )}
      {view === "risk" && (
        <>
          <div className="risk-context">
            <p>
              <strong>{number(data.overview.customers)}</strong> scored subscribers <span>·</span>{" "}
              {shortDate(data.overview.score_cutoff)}
            </p>
            <p>
              High ≥40% <span>·</span> Watch 20–40% <span>·</span> Lower &lt;20%
            </p>
          </div>
          <section className="panel risk-panel">
            <RiskFiltersForm
              key={`${applied.search}|${applied.band}|${applied.auto}|${offset}`}
              applied={applied}
              apply={(filters) => router.push(riskHref(filters, 0), { scroll: false })}
              clear={clear}
            />
            <div className="table-caption">
              <h2>Ranked subscribers</h2>
              <span role="status">{number(data.risk.total)} matches</span>
            </div>
            {data.risk.items.length ? (
              <RiskTable items={data.risk.items} open={openCustomer} />
            ) : data.risk.total ? (
              <div className="empty-state">
                <h3>This page is outside the current results</h3>
                <p>The published cohort or result count may have changed. Open the first page.</p>
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => router.push(riskHref(applied, 0), { scroll: false })}
                >
                  Go to first page
                </button>
              </div>
            ) : (
              <div className="empty-state">
                <h3>No subscribers match these filters</h3>
                <p>Try a different subscriber ID or broaden the risk and renewal filters.</p>
                <button type="button" className="button secondary" onClick={clear}>
                  Clear filters
                </button>
              </div>
            )}
            <div className="pagination">
              <p>
                {data.risk.items.length
                  ? `${offset + 1}–${Math.min(offset + pageSize, data.risk.total)} of ${number(data.risk.total)}`
                  : data.risk.total
                    ? `0 shown of ${number(data.risk.total)} matches`
                    : "0 results"}
              </p>
              <div>
                <button
                  type="button"
                  className="button secondary"
                  disabled={offset === 0}
                  onClick={() =>
                    router.push(riskHref(applied, Math.max(0, offset - pageSize)), {
                      scroll: false,
                    })
                  }
                  aria-label="Previous page"
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="button secondary"
                  disabled={offset + pageSize >= data.risk.total}
                  onClick={() =>
                    router.push(riskHref(applied, offset + pageSize), { scroll: false })
                  }
                  aria-label="Next page"
                >
                  Next
                </button>
              </div>
            </div>
          </section>
        </>
      )}
      {view === "cohorts" && <CohortsView data={data} />}
      {view === "status" && <StatusView data={data} />}
      <dialog
        ref={dialog}
        className="customer-dialog"
        aria-labelledby="customer-title"
        onClose={() => {
          detailRequest.current?.abort();
          setDetail(null);
        }}
        onClick={(event) => {
          if (event.target === event.currentTarget) dialog.current?.close();
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            dialog.current?.close();
          }
        }}
      >
        <div className="dialog-content">
          <div className="section-heading">
            <h2 id="customer-title">Subscriber review</h2>
            <button
              type="button"
              className="icon-button"
              aria-label="Close customer details"
              onClick={() => dialog.current?.close()}
            >
              ×
            </button>
          </div>
          {detail?.kind === "loading" && <p role="status">Loading {detail.id}…</p>}
          {detail?.kind === "error" && <p role="alert">{detail.message}</p>}
          {detail?.kind === "ready" && (
            <>
              <p className="detail-id">{detail.data.customer_id}</p>
              <div className="detail-risk">
                <strong>{percent(detail.data.churn_probability)}</strong>
                <span className={`badge ${detail.data.risk_band}`}>
                  {bandName[detail.data.risk_band]} risk
                </span>
              </div>
              <p className="caption">
                Historical churn probability at {shortDate(detail.data.as_of_date)}
              </p>
              <h3>Observed inputs</h3>
              <dl className="feature-list">
                {Object.entries(detail.data.features).map(([name, value]) => (
                  <div key={name}>
                    <dt>{featureNames[name] || name}</dt>
                    <dd>{name === "auto_renew" ? (value ? "On" : "Off") : value}</dd>
                  </div>
                ))}
              </dl>
              <div className="detail-provenance">
                <p>Latest contributing event: {shortDate(detail.data.feature_max_event_at)}</p>
                <p>Latest source availability: {shortDate(detail.data.source_max_available_at)}</p>
                <p className="caption">
                  These are observed model inputs, not causal explanations. The score and details
                  use the same pinned model release.
                </p>
                <details>
                  <summary>Model and source identifiers</summary>
                  <code>{detail.data.model_version}</code>
                  <code>{detail.data.source_release_id}</code>
                </details>
              </div>
            </>
          )}
        </div>
      </dialog>
    </Frame>
  );
}
