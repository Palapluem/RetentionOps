"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";
import {
  createLocalInsight,
  type LocalInsight,
  number,
  percent,
  readData,
  type SystemData,
  shortDate,
  timestamp,
} from "../lib/data";
import { Frame, RunHistoryTable } from "./workspace";

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: SystemData };

type InsightState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "result"; data: LocalInsight };

const insightReason: Record<NonNullable<LocalInsight["reason"]>, string> = {
  no_publication: "Publish a local synthetic release before requesting an insight.",
  publication_unavailable:
    "The active publication could not be verified. Check System status first.",
  runtime_unavailable: "The local Ollama runtime is not responding. The dashboard is unaffected.",
  model_not_installed: "The configured model is not installed in the local Ollama runtime.",
  timeout: "Local inference took too long. Retry after checking the Ollama runtime.",
  runtime_busy: "Another local insight is being generated. Wait for it to finish.",
  rate_limited: "Wait 10 seconds between local insight requests, then retry.",
  invalid_response: "The local model returned an unsupported response. No insight was shown.",
  unsafe_runtime_url: "The configured model endpoint is outside the approved local boundary.",
};

const artifactLabels: Record<SystemData["model_artifact_state"], string> = {
  not_published: "Awaiting publication",
  verified: "Checksum verified",
  missing: "Artifact missing",
  mismatch: "Checksum mismatch",
  unavailable: "Could not verify",
};

function ScrollableTable({ children }: { children: ReactNode }) {
  return (
    // biome-ignore lint/a11y/noNoninteractiveTabindex: Overflowing tables require a keyboard focus target, verified by browser tests.
    <section className="table-scroll" aria-label="Mature cohort denominators table" tabIndex={0}>
      {children}
    </section>
  );
}

export default function SystemView() {
  const [revision, setRevision] = useState(0);
  return <SystemContent key={revision} refresh={() => setRevision((value) => value + 1)} />;
}

function SystemContent({ refresh }: { refresh: () => void }) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [insight, setInsight] = useState<InsightState>({ kind: "idle" });

  useEffect(() => {
    const controller = new AbortController();
    readData<SystemData>("system-status", controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ kind: "ready", data });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({
            kind: "error",
            message:
              error instanceof Error ? error.message : "Retry after the data service recovers.",
          });
      });
    return () => controller.abort();
  }, []);

  if (state.kind === "loading")
    return (
      <Frame view="system" refresh={refresh}>
        <section className="panel loading-state" role="status">
          Loading system status…
        </section>
      </Frame>
    );
  if (state.kind === "error")
    return (
      <Frame view="system" refresh={refresh}>
        <section className="panel error-state" role="alert">
          <h2>System status could not be loaded</h2>
          <p>{state.message}</p>
          <button type="button" className="button primary" onClick={refresh}>
            Retry
          </button>
        </section>
      </Frame>
    );

  const data = state.data;
  const active = data.active_release;
  const quality = data.quality_summary;
  const ready = data.publication_state === "ready";
  const latest = data.runs[0];
  const attention =
    ready && (data.model_artifact_state !== "verified" || latest?.state === "failed");
  const stageValue = ready
    ? "Published"
    : data.publication_state === "empty"
      ? "Awaiting publication"
      : "Could not verify";
  const stages = [
    {
      name: "Source",
      value: active
        ? active.event_release_id
          ? "Synthetic events"
          : "Synthetic snapshots"
        : stageValue,
    },
    { name: "Features", value: active ? `${active.features.length} approved inputs` : stageValue },
    {
      name: "Selected model",
      value: active
        ? active.model_family === "lightgbm"
          ? "LightGBM"
          : "Logistic Regression"
        : stageValue,
    },
    {
      name: "Scores",
      value: ready ? `${number(data.scored_customers ?? 0)} rows reconciled` : stageValue,
    },
    { name: "Read API", value: "Responding" },
  ];

  const requestInsight = async () => {
    setInsight({ kind: "loading" });
    try {
      setInsight({ kind: "result", data: await createLocalInsight() });
    } catch (error) {
      setInsight({
        kind: "error",
        message: error instanceof Error ? error.message : "Local insight is unavailable.",
      });
    }
  };

  return (
    <Frame view="system" refresh={refresh} cutoff={data.score_cutoff ?? undefined}>
      <section className="panel system-summary" aria-label="Local system state">
        <div>
          <span
            className={`badge ${ready && !attention ? "low" : data.publication_state === "empty" ? "neutral" : "watch"}`}
          >
            {attention
              ? "Attention"
              : ready
                ? "Serving"
                : data.publication_state === "empty"
                  ? "Awaiting first run"
                  : "Unavailable"}
          </span>
          <h2>
            {ready
              ? "The active release is serving"
              : data.publication_state === "empty"
                ? "Publish the first local release"
                : "Check the active publication"}
          </h2>
          <p>{data.message}</p>
          {latest?.state === "failed" && ready && (
            <p className="system-notice">
              The latest attempt failed. The previous successful release remains active.
            </p>
          )}
        </div>
        <div className="system-observed">
          <span>Checked</span>
          <strong>{timestamp(data.observed_at)}</strong>
          <span>Local synthetic environment</span>
        </div>
      </section>

      <ol className="system-flow" aria-label="Local pipeline stages">
        {stages.map((stage, index) => (
          <li key={stage.name} className={ready || index === 4 ? "stage-ready" : "stage-waiting"}>
            <span className="stage-dot" aria-hidden="true" />
            <h2>{stage.name}</h2>
            <p>{stage.value}</p>
          </li>
        ))}
      </ol>

      <div className="two-column">
        <section className="panel">
          <div className="section-heading">
            <h2>Active release</h2>
            <Link className="text-link" href="/status">
              Inspect data & model
            </Link>
          </div>
          {active ? (
            <dl className="lineage">
              <dt>Selected estimator</dt>
              <dd>{active.model_family === "lightgbm" ? "LightGBM" : "Logistic Regression"}</dd>
              <dt>Candidate</dt>
              <dd>{active.selected_candidate}</dd>
              <dt>Validation AP</dt>
              <dd>{active.validation_average_precision?.toFixed(3) ?? "Legacy fixed baseline"}</dd>
              <dt>Scored rows</dt>
              <dd>{number(data.scored_customers ?? 0)}</dd>
              <dt>Historical cutoff</dt>
              <dd>{data.score_cutoff ? shortDate(data.score_cutoff) : "Unavailable"}</dd>
              <dt>Model artifact</dt>
              <dd
                className={
                  data.model_artifact_state === "verified" ? "system-ok" : "system-warning"
                }
              >
                {artifactLabels[data.model_artifact_state]}
              </dd>
              <dt>Model version</dt>
              <dd>
                <code>{active.model_version}</code>
              </dd>
            </dl>
          ) : (
            <p className="empty-state">
              {data.publication_state === "empty"
                ? "No successful release is published yet. Complete a synthetic pipeline run, then refresh this view."
                : "Release details cannot be trusted until the publication is repaired. Pipeline attempts below may help identify the failure."}
            </p>
          )}
          {active && (
            <details className="hash-details">
              <summary>Source & artifact evidence</summary>
              <dl className="lineage">
                <dt>Source release</dt>
                <dd>
                  <code>{active.source_release_id}</code>
                </dd>
                <dt>Event release</dt>
                <dd>
                  <code>{active.event_release_id || "Snapshot source"}</code>
                </dd>
                <dt>Dataset SHA-256</dt>
                <dd>
                  <code>{active.dataset_sha256}</code>
                </dd>
                <dt>Model SHA-256</dt>
                <dd>
                  <code>{active.model_sha256}</code>
                </dd>
              </dl>
            </details>
          )}
        </section>
        <section className="panel source-truth">
          <div className="section-heading">
            <h2>Source ground truth</h2>
            <span className="badge synthetic">Simulated labels</span>
          </div>
          <p>{data.source_truth.label_definition}</p>
          <dl className="lineage">
            <dt>Scored source</dt>
            <dd>{active ? "Project-generated synthetic records" : "No active scored source"}</dd>
            <dt>External data</dt>
            <dd>No approved external source connected</dd>
            <dt>Source coverage</dt>
            <dd>
              {active?.source_complete_through
                ? shortDate(active.source_complete_through)
                : "No event watermark available"}
            </dd>
          </dl>
          <p className="caption">
            Real-data use requires approved source rights, eligibility and outcome definitions.
          </p>
        </section>
      </div>

      <section className="panel" aria-labelledby="data-quality-heading">
        <div className="section-heading">
          <div>
            <h2 id="data-quality-heading">Data quality & model health</h2>
            <p className="caption">Checks and metrics from the active synthetic release.</p>
          </div>
          <span className={`badge ${quality ? "low" : "neutral"}`}>
            {quality ? "Release reconciled" : "No active release"}
          </span>
        </div>
        {quality ? (
          <>
            <dl className="quality-metrics">
              <div>
                <dt>Source path</dt>
                <dd>{quality.source_kind === "event_derived" ? "Event-derived" : "Snapshots"}</dd>
                <dd className="quality-detail">
                  {number(quality.source_rows)}{" "}
                  {quality.source_kind === "event_derived" ? "event revisions" : "snapshot rows"}
                </dd>
              </div>
              <div>
                <dt>Feature rows</dt>
                <dd>{number(quality.feature_rows)}</dd>
                <dd className="quality-detail">
                  {quality.excluded_rows === null
                    ? "No exclusion counter on the snapshot path"
                    : `${number(quality.eligible_rows)} eligible · ${number(quality.excluded_rows)} excluded`}
                </dd>
              </div>
              <div>
                <dt>Completeness</dt>
                <dd>
                  {quality.source_coverage_status === "verified" && quality.source_complete_through
                    ? `Through ${shortDate(quality.source_complete_through)}`
                    : "Watermark not declared"}
                </dd>
                <dd className="quality-detail">
                  {quality.source_coverage_status === "verified" && quality.source_complete_through
                    ? `Evaluation freeze ${shortDate(quality.evaluation_freeze)}`
                    : `Label maturity verified at ${shortDate(quality.evaluation_freeze)}`}
                </dd>
              </div>
              <div>
                <dt>Test average precision</dt>
                <dd>{quality.test_average_precision.toFixed(3)}</dd>
                <dd className="quality-detail">
                  Constant-prior reference {quality.baseline_average_precision.toFixed(3)}
                </dd>
              </div>
              <div>
                <dt>Test Brier score</dt>
                <dd>{quality.test_brier.toFixed(3)}</dd>
                <dd className="quality-detail">
                  Lower is better for probabilistic calibration error
                </dd>
              </div>
              <div>
                <dt>Recall at 10% review capacity</dt>
                <dd>{percent(quality.recall_at_10pct)}</dd>
                <dd className="quality-detail">Historical synthetic holdout</dd>
              </div>
            </dl>
            <ScrollableTable>
              <table aria-label="Mature cohort denominators">
                <thead>
                  <tr>
                    <th scope="col">Cutoff</th>
                    <th scope="col">Partition</th>
                    <th scope="col">Eligible</th>
                    <th scope="col">Mature churned</th>
                    <th scope="col">Observed churn</th>
                  </tr>
                </thead>
                <tbody>
                  {quality.cohorts.map((cohort) => (
                    <tr key={`${cohort.as_of_date}-${cohort.partition}`}>
                      <td>{shortDate(cohort.as_of_date)}</td>
                      <td>{cohort.partition}</td>
                      <td>{number(cohort.eligible)}</td>
                      <td>{number(cohort.churned)}</td>
                      <td>{percent(cohort.churn_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollableTable>
            <p className="caption quality-footnote">
              {number(quality.scored_rows)} selected-model test scores reconciled to the active
              release; label maturity {quality.label_maturity_status}.{" "}
              {quality.source_kind === "snapshot"
                ? "The snapshot path does not declare an event completeness watermark."
                : "The event path verifies that source completeness covers the evaluation freeze."}{" "}
              Metrics describe historical synthetic data, not live outcomes.
            </p>
          </>
        ) : (
          <p className="empty-state">
            Quality and model checks appear after the first valid local publication.
          </p>
        )}
      </section>

      <section className="panel local-insight" aria-labelledby="local-insight-heading">
        <div className="section-heading">
          <div>
            <h2 id="local-insight-heading">Optional local AI insight</h2>
            <p className="caption">
              Ollama selects from verified aggregate observations. No customer-level records or
              free-text prompt are sent.
            </p>
          </div>
          <span className="badge neutral">Local model · no API key</span>
        </div>
        <button
          type="button"
          className="button primary"
          onClick={requestInsight}
          disabled={!quality || insight.kind === "loading"}
        >
          {insight.kind === "loading" ? "Generating locally…" : "Generate insight"}
        </button>
        {insight.kind === "idle" && (
          <p className="caption insight-status">
            This runs only when requested. Install the configured local model to enable it.
          </p>
        )}
        {insight.kind === "loading" && (
          <p className="caption insight-status" role="status" aria-live="polite">
            Asking the local model to select evidence-based observations…
          </p>
        )}
        {insight.kind === "error" && (
          <p className="system-warning insight-status" role="alert">
            {insight.message}
          </p>
        )}
        {insight.kind === "result" &&
          insight.data.status === "unavailable" &&
          insight.data.reason && (
            <p className="insight-status" role="status" aria-live="polite">
              {insightReason[insight.data.reason]}
            </p>
          )}
        {insight.kind === "result" && insight.data.status === "ready" && (
          <div className="insight-result" role="status" aria-live="polite">
            <ul>
              {(insight.data.observations ?? []).map((observation) => (
                <li key={observation.id}>{observation.text}</li>
              ))}
            </ul>
            {insight.data.next_step && (
              <p>
                <strong>Suggested next check:</strong> {insight.data.next_step}
              </p>
            )}
            <p className="caption">
              Advisory only · {insight.data.model} · cutoff{" "}
              {insight.data.score_cutoff ? shortDate(insight.data.score_cutoff) : "unknown"} ·
              release <code>{insight.data.model_version}</code>
            </p>
            <p className="caption">
              The local model chooses approved observations; RetentionOps renders their verified
              values. No causal, ROI, or live-performance claim is produced.
            </p>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>Pipeline attempts</h2>
          <span className="subtle-label">Latest 10 recorded stage attempts</span>
        </div>
        <RunHistoryTable
          runs={data.runs}
          label="System pipeline attempts"
          emptyMessage="No pipeline attempt is recorded. Run the synthetic pipeline to begin."
        />
        <p className="caption">
          Source stages count event revisions; model stages count scored customers. Attempt state is
          the last recorded transition.
        </p>
      </section>
      <section className="panel">
        <div className="section-heading">
          <h2>Infrastructure readiness</h2>
          <span className="badge neutral">Local</span>
        </div>
        <dl className="infrastructure-list">
          <div>
            <dt>Score store</dt>
            <dd>
              {data.infrastructure.score_store}
              <small>Read-only API access</small>
            </dd>
          </div>
          <div>
            <dt>Google Cloud</dt>
            <dd>
              Not connected<small>Account, region, budget and IAM review pending</small>
            </dd>
          </div>
          <div>
            <dt>API authentication</dt>
            <dd>
              Not configured<small>Local loopback demo scope</small>
            </dd>
          </div>
        </dl>
      </section>
    </Frame>
  );
}
