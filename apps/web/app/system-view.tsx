"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { number, readData, type SystemData, shortDate, timestamp } from "../lib/data";
import { Frame, RunHistoryTable } from "./workspace";

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: SystemData };

const artifactLabels: Record<SystemData["model_artifact_state"], string> = {
  not_published: "Awaiting publication",
  verified: "Checksum verified",
  missing: "Artifact missing",
  mismatch: "Checksum mismatch",
  unavailable: "Could not verify",
};

export default function SystemView() {
  const [revision, setRevision] = useState(0);
  return <SystemContent key={revision} refresh={() => setRevision((value) => value + 1)} />;
}

function SystemContent({ refresh }: { refresh: () => void }) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

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
