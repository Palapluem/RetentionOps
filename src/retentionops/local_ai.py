"""Optional local-only Ollama insights over an allowlisted aggregate snapshot."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field

from .serving import Contract, DataQualitySummary

ObservationId = Literal[
    "event_coverage_verified",
    "snapshot_watermark_not_declared",
    "publication_reconciled",
    "model_above_baseline",
    "model_not_above_baseline",
    "test_cohort_mature",
    "exclusions_present",
]
NextStepId = Literal[
    "review_cohort_denominators",
    "compare_validation_and_holdout",
    "confirm_source_watermark",
]
UnavailableReason = Literal[
    "no_publication",
    "publication_unavailable",
    "runtime_unavailable",
    "model_not_installed",
    "timeout",
    "runtime_busy",
    "rate_limited",
    "invalid_response",
    "unsafe_runtime_url",
]


class InsightObservation(Contract):
    id: ObservationId
    text: str


class LocalInsight(Contract):
    status: Literal["ready", "unavailable"]
    generated_at: datetime
    model: str | None
    source_release_id: str | None
    model_version: str | None
    score_cutoff: date | None
    advisory_only: Literal[True] = True
    observations: list[InsightObservation] = Field(default_factory=list, max_length=3)
    next_step: str | None
    reason: UnavailableReason | None


class _ModelSelection(Contract):
    observation_ids: list[ObservationId] = Field(max_length=2)
    next_step: NextStepId


def _base_url_is_local(base_url: str) -> bool:
    try:
        parsed = urlsplit(base_url)
        return (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost", "ollama"}
            and parsed.port == 11434
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and parsed.query == ""
            and parsed.fragment == ""
        )
    except ValueError:
        return False


def _observation_ids(summary: DataQualitySummary) -> list[str]:
    choices = [
        "publication_reconciled",
        "test_cohort_mature",
        "model_above_baseline"
        if summary.test_average_precision > summary.baseline_average_precision
        else "model_not_above_baseline",
    ]
    choices.append(
        "event_coverage_verified"
        if summary.source_coverage_status == "verified"
        else "snapshot_watermark_not_declared"
    )
    if summary.excluded_rows is not None and summary.excluded_rows > 0:
        choices.append("exclusions_present")
    return choices


def _next_step_ids(summary: DataQualitySummary) -> list[str]:
    steps = ["review_cohort_denominators", "compare_validation_and_holdout"]
    if summary.source_coverage_status != "verified":
        steps.append("confirm_source_watermark")
    return steps


def _facts(summary: DataQualitySummary) -> dict:
    """Build an explicit minimal payload; never add identifiers or row-level values."""
    return {
        "data_mode": summary.data_mode,
        "source_kind": summary.source_kind,
        "source_coverage_status": summary.source_coverage_status,
        "source_complete_through": (
            summary.source_complete_through.isoformat() if summary.source_complete_through else None
        ),
        "evaluation_freeze": summary.evaluation_freeze.isoformat(),
        "score_cutoff": summary.score_cutoff.isoformat(),
        "source_rows": summary.source_rows,
        "eligible_rows": summary.eligible_rows,
        "excluded_rows": summary.excluded_rows,
        "feature_rows": summary.feature_rows,
        "scored_rows": summary.scored_rows,
        "reconciliation_status": summary.reconciliation_status,
        "label_maturity_status": summary.label_maturity_status,
        "test_cohort_rows": summary.test_cohort_rows,
        "test_churned": summary.test_churned,
        "test_churn_rate": round(summary.test_churn_rate, 4),
        "test_average_precision": round(summary.test_average_precision, 4),
        "baseline_average_precision": round(summary.baseline_average_precision, 4),
        "test_brier": round(summary.test_brier, 4),
        "recall_at_10pct": round(summary.recall_at_10pct, 4),
    }


def _schema(observations: list[str], next_steps: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "observation_ids": {
                "type": "array",
                "items": {"type": "string", "enum": observations},
                "maxItems": 2,
                "uniqueItems": True,
            },
            "next_step": {"type": "string", "enum": next_steps},
        },
        "required": ["observation_ids", "next_step"],
        "additionalProperties": False,
    }


def _request_model(
    *, base_url: str, model: str, facts: dict, observations: list[str], next_steps: list[str]
) -> dict:
    selection_contract = _schema(observations, next_steps)
    instructions = (
        "You are a local analyst helper for a synthetic-data demo. Return only JSON matching "
        "the supplied schema. Choose up to two observation IDs that are directly supported by "
        "the facts and exactly one allowed next-step ID. Do not write prose, numbers, causes, "
        "ROI, campaign claims, or any new facts. If evidence is limited, prefer source and "
        "denominator checks."
    )
    content = json.dumps(
        {
            "aggregate_facts": facts,
            "allowed_observation_ids": observations,
            "allowed_next_step_ids": next_steps,
        },
        separators=(",", ":"),
    )
    request_body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": content},
            ],
            "format": selection_contract,
            "stream": False,
            "think": False,
            "keep_alive": "2m",
            "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 96},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Ignore proxy environment variables so even misconfigured HTTP_PROXY cannot forward facts.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=45) as response:
        raw = response.read(16_385)
    if len(raw) > 16_384:
        raise ValueError("Model response exceeds the local output bound")
    response_body = json.loads(raw)
    if not isinstance(response_body, dict) or not isinstance(response_body.get("message"), dict):
        raise ValueError("Model response has an invalid shape")
    content = response_body["message"].get("content")
    if not isinstance(content, str) or len(content) > 4_096:
        raise ValueError("Model response has an invalid shape")
    selection = _ModelSelection.model_validate_json(content)
    if (
        len(selection.observation_ids) != len(set(selection.observation_ids))
        or any(value not in observations for value in selection.observation_ids)
        or selection.next_step not in next_steps
    ):
        raise ValueError("Model response selected unsupported evidence")
    return selection.model_dump()


def _observation_text(observation_id: str, summary: DataQualitySummary) -> str:
    if observation_id == "event_coverage_verified":
        return (
            "Event-source completeness is verified through "
            f"{summary.source_complete_through:%Y-%m-%d}, covering the "
            f"{summary.evaluation_freeze:%Y-%m-%d} evaluation freeze."
        )
    if observation_id == "snapshot_watermark_not_declared":
        return (
            "The snapshot path verifies label maturity, but it does not declare an event-source "
            "completeness watermark."
        )
    if observation_id == "publication_reconciled":
        return "Published feature cohorts and the selected test scores passed row reconciliation."
    if observation_id == "model_above_baseline":
        return (
            "On this synthetic historical holdout, selected-model average precision is "
            f"{summary.test_average_precision:.3f}, above the constant-prior reference "
            f"{summary.baseline_average_precision:.3f}. This does not establish live performance."
        )
    if observation_id == "model_not_above_baseline":
        return (
            "On this synthetic historical holdout, selected-model average precision is "
            f"{summary.test_average_precision:.3f}, at or below the constant-prior reference "
            f"{summary.baseline_average_precision:.3f}. This does not establish live performance."
        )
    if observation_id == "test_cohort_mature":
        return (
            f"The evaluated test cohort has {summary.test_cohort_rows:,} mature rows; "
            f"{summary.test_churned:,} are labeled churned "
            f"({summary.test_churn_rate:.1%})."
        )
    if observation_id == "exclusions_present":
        return (
            f"Feature derivation excluded {summary.excluded_rows:,} opportunities without a "
            "known subscription."
        )
    raise ValueError("Unknown local insight observation")


_NEXT_STEP_TEXT = {
    "review_cohort_denominators": "Review eligible and churned denominators across the cohorts.",
    "compare_validation_and_holdout": "Compare validation selection evidence with the frozen holdout metrics.",
    "confirm_source_watermark": "Confirm the next source completeness watermark before replaying events.",
}
_INFERENCE_LOCK = threading.Lock()
_INFERENCE_COOLDOWN_SECONDS = 10
_LAST_INFERENCE_AT = 0.0


def _unavailable(reason: UnavailableReason) -> LocalInsight:
    return LocalInsight(
        status="unavailable",
        generated_at=datetime.now(UTC),
        model=None,
        source_release_id=None,
        model_version=None,
        score_cutoff=None,
        next_step=None,
        reason=reason,
    )


def generate_insight(
    summary: DataQualitySummary | None, publication_state: str = "ready"
) -> LocalInsight:
    """Ask one loopback model to select among verified, pre-rendered aggregate observations."""
    global _LAST_INFERENCE_AT
    if summary is None:
        return _unavailable(
            "publication_unavailable" if publication_state == "unavailable" else "no_publication"
        )
    base_url = os.getenv("RETENTIONOPS_OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.getenv("RETENTIONOPS_OLLAMA_MODEL", "qwen3:4b-instruct")
    if not _base_url_is_local(base_url) or not re.fullmatch(r"[a-z0-9][a-z0-9._:-]{0,79}", model):
        return _unavailable("unsafe_runtime_url")
    if model.endswith(":cloud") or model.endswith("-cloud"):
        return _unavailable("unsafe_runtime_url")

    available_observations = _observation_ids(summary)
    available_steps = _next_step_ids(summary)
    if not _INFERENCE_LOCK.acquire(blocking=False):
        return _unavailable("runtime_busy")
    try:
        now = time.monotonic()
        if now - _LAST_INFERENCE_AT < _INFERENCE_COOLDOWN_SECONDS:
            return _unavailable("rate_limited")
        _LAST_INFERENCE_AT = now
        try:
            selected = _request_model(
                base_url=base_url,
                model=model,
                facts=_facts(summary),
                observations=available_observations,
                next_steps=available_steps,
            )
        except urllib.error.HTTPError as exc:
            return _unavailable("model_not_installed" if exc.code == 404 else "runtime_unavailable")
        except TimeoutError:
            return _unavailable("timeout")
        except urllib.error.URLError as exc:
            return _unavailable(
                "timeout" if isinstance(exc.reason, TimeoutError) else "runtime_unavailable"
            )
        except (ValueError, TypeError, KeyError):
            return _unavailable("invalid_response")
        except OSError:
            return _unavailable("runtime_unavailable")
    finally:
        _INFERENCE_LOCK.release()

    if (
        any(value not in available_observations for value in selected["observation_ids"])
        or selected["next_step"] not in available_steps
    ):
        return _unavailable("invalid_response")
    return LocalInsight(
        status="ready",
        generated_at=datetime.now(UTC),
        model=model,
        source_release_id=summary.source_release_id,
        model_version=summary.model_version,
        score_cutoff=summary.score_cutoff,
        observations=[
            InsightObservation(
                id=observation_id,
                text=_observation_text(observation_id, summary),
            )
            for observation_id in selected["observation_ids"]
        ],
        next_step=_NEXT_STEP_TEXT[selected["next_step"]],
        reason=None,
    )
