"""Explicit, optional cloud publication for validated synthetic event releases."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from .data import canonical_hash, sha256_file
from .events import load_event_source

_PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_RELEASE_ID = re.compile(r"^[a-z][a-z0-9-]{0,39}-[0-9a-f]{64}$")
_DATASET_OR_TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")
_BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")
_LOCATION = re.compile(r"^[A-Za-z0-9_-]{1,30}$")
_BRONZE_SCHEMA = (
    ("source_release_id", "STRING", "REQUIRED"),
    ("source_id", "STRING", "REQUIRED"),
    ("source_sha256", "STRING", "REQUIRED"),
    ("schema_version", "STRING", "REQUIRED"),
    ("complete_through", "DATE", "REQUIRED"),
    ("event_id", "STRING", "REQUIRED"),
    ("revision", "INTEGER", "REQUIRED"),
    ("customer_id", "STRING", "REQUIRED"),
    ("kind", "STRING", "REQUIRED"),
    ("occurred_at", "DATE", "REQUIRED"),
    ("available_at", "DATE", "REQUIRED"),
    ("deleted", "BOOLEAN", "REQUIRED"),
    ("expiry_date", "DATE", "NULLABLE"),
    ("started_at", "DATE", "NULLABLE"),
    ("monthly_fee", "FLOAT", "NULLABLE"),
    ("auto_renew", "INTEGER", "NULLABLE"),
    ("source_type", "STRING", "REQUIRED"),
    ("event_sha256", "STRING", "REQUIRED"),
)
_TYPE_ALIASES = {
    "INT64": "INTEGER",
    "FLOAT64": "FLOAT",
    "BOOL": "BOOLEAN",
}
_MAX_LOAD_ATTEMPTS = 3


def _validated_destination(destination: str) -> tuple[str, str, str]:
    parts = destination.split(".")
    if (
        len(parts) != 3
        or not _PROJECT_ID.fullmatch(parts[0])
        or not _DATASET_OR_TABLE.fullmatch(parts[1])
        or not _DATASET_OR_TABLE.fullmatch(parts[2])
    ):
        raise ValueError("BigQuery table must be a fully qualified project.dataset.table name")
    return parts[0], parts[1], parts[2]


def _validated_cloud_inputs(bucket_name: str, location: str) -> None:
    if (
        not _BUCKET_NAME.fullmatch(bucket_name)
        or ".." in bucket_name
        or bucket_name.endswith((".-", "-."))
    ):
        raise ValueError("Invalid Cloud Storage bucket name")
    if not _LOCATION.fullmatch(location):
        raise ValueError("An explicit valid Cloud Storage / BigQuery location is required")


def _validated_source_manifest(manifest: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(manifest, dict):
        raise ValueError("Invalid event source manifest")
    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("Invalid event source manifest")
    source_id = identity.get("source_id")
    source_release_id = manifest.get("source_release_id")
    expected_identity_fields = {
        "source_id",
        "sha256",
        "source_type",
        "schema_version",
        "complete_through",
    }
    if (
        set(identity) != expected_identity_fields
        or not isinstance(source_id, str)
        or not re.fullmatch(r"^[a-z][a-z0-9-]{0,39}$", source_id)
        or not isinstance(source_release_id, str)
        or not _RELEASE_ID.fullmatch(source_release_id)
        or not source_release_id.startswith(source_id + "-")
        or identity.get("source_type") != "SYNTHETIC"
        or identity.get("schema_version") != "subscription-events-v1"
        or not isinstance(identity.get("sha256"), str)
        or not re.fullmatch(r"^[0-9a-f]{64}$", identity["sha256"])
    ):
        raise ValueError("Invalid synthetic event source identity")
    try:
        date.fromisoformat(identity["complete_through"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid event source completeness watermark") from exc
    if source_release_id != f"{source_id}-{canonical_hash(identity)}":
        raise ValueError("Event source release ID does not match its identity")
    if any(manifest.get(key) != value for key, value in identity.items()):
        raise ValueError("Event source manifest fields do not match its identity")
    rows = manifest.get("rows")
    quality = manifest.get("quality")
    if (
        type(rows) is not int
        or rows < 1
        or not isinstance(quality, dict)
        or type(quality.get("rows")) is not int
        or quality.get("rows") != rows
    ):
        raise ValueError("Event source manifest row counts are invalid")
    return source_id, source_release_id


def _validated_bronze_uri(bronze_uri: str, manifest: dict[str, Any], location: str) -> None:
    source_id, source_release_id = _validated_source_manifest(manifest)
    if not isinstance(bronze_uri, str):
        raise ValueError("BigQuery source URI must target this release's bronze artifact")
    match = re.fullmatch(
        r"gs://(?P<bucket>[a-z0-9][a-z0-9._-]{1,61}[a-z0-9])"
        r"/retentionops/(?P<source>[a-z][a-z0-9-]{0,39})/"
        r"(?P<release>[a-z][a-z0-9-]{0,39}-[0-9a-f]{64})/bronze/events\.ndjson",
        bronze_uri,
    )
    if (
        match is None
        or match.group("source") != source_id
        or match.group("release") != source_release_id
    ):
        raise ValueError("BigQuery source URI must target this release's bronze artifact")
    _validated_cloud_inputs(match.group("bucket"), location)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_event_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return _sha256_bytes(encoded.encode("utf-8"))


def _exception_code(error: Exception) -> int | None:
    code = getattr(error, "code", None)
    if callable(code):
        code = code()
    try:
        return int(code)
    except (TypeError, ValueError):
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
        try:
            return int(status)
        except (TypeError, ValueError):
            return None


def _artifact_metadata(
    source_release_id: str, artifact_kind: str, checksum: str, row_count: int
) -> dict[str, str]:
    return {
        "source_release_id": source_release_id,
        "artifact_kind": artifact_kind,
        "sha256": checksum,
        "row_count": str(row_count),
    }


def _upload_immutable_blob(
    bucket: Any,
    object_name: str,
    path: Path,
    *,
    source_release_id: str,
    artifact_kind: str,
    row_count: int,
    content_type: str,
) -> dict[str, str]:
    checksum = sha256_file(path)
    expected_metadata = _artifact_metadata(source_release_id, artifact_kind, checksum, row_count)
    blob = bucket.blob(object_name)
    blob.metadata = expected_metadata
    try:
        blob.upload_from_filename(
            str(path), content_type=content_type, if_generation_match=0, checksum="auto"
        )
        status = "UPLOADED"
    except Exception as exc:
        if _exception_code(exc) != 412:
            raise
        blob = bucket.blob(object_name)
        blob.reload()
        if blob.metadata != expected_metadata:
            raise ValueError(
                "Existing Cloud Storage object metadata conflicts with this release"
            ) from None
        existing_checksum = _sha256_bytes(blob.download_as_bytes())
        if existing_checksum != checksum:
            raise ValueError(
                "Existing Cloud Storage object checksum conflicts with this release"
            ) from None
        status = "ALREADY_PRESENT"
    if blob.generation is None:
        blob.reload()
    if blob.generation is None:
        raise ValueError("Cloud Storage did not return an object generation")
    return {
        "uri": f"gs://{bucket.name}/{object_name}",
        "generation": str(blob.generation),
        "sha256": checksum,
        "status": status,
    }


def _write_bronze_ndjson(path: Path, events: list, manifest: dict) -> None:
    identity = manifest["identity"]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            payload = event.model_dump(mode="json")
            row = {
                "source_release_id": manifest["source_release_id"],
                "source_id": identity["source_id"],
                "source_sha256": identity["sha256"],
                "schema_version": identity["schema_version"],
                "complete_through": identity["complete_through"],
                **payload,
                "event_sha256": _canonical_event_hash(payload),
            }
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False))
            handle.write("\n")


def publish_event_release_to_gcs(
    root: Path,
    source_release_id: str,
    *,
    client: Any,
    bucket_name: str,
    location: str,
    max_upload_bytes: int,
) -> dict[str, Any]:
    """Publish exact raw bytes, manifest and a typed bronze load file to an existing bucket."""
    _validated_cloud_inputs(bucket_name, location)
    if type(max_upload_bytes) is not int or max_upload_bytes < 1:
        raise ValueError("max_upload_bytes must be a positive integer")
    if not _RELEASE_ID.fullmatch(source_release_id):
        raise ValueError("Invalid source release ID")
    release_root = Path(root).resolve() / "data" / "events" / source_release_id
    raw_path = release_root / "events.jsonl"
    manifest_path = release_root / "manifest.json"
    if raw_path.is_file() and raw_path.stat().st_size > max_upload_bytes:
        raise ValueError("Raw source exceeds max_upload_bytes")
    if manifest_path.is_file() and manifest_path.stat().st_size > max_upload_bytes:
        raise ValueError("Source manifest exceeds max_upload_bytes")
    events, manifest = load_event_source(root, source_release_id)
    source_id = manifest["identity"]["source_id"]

    prefix = f"retentionops/{source_id}/{source_release_id}"
    with tempfile.TemporaryDirectory(prefix="retentionops-bronze-") as temp_dir:
        staged = Path(temp_dir)
        staged_raw = staged / "events.jsonl"
        staged_manifest = staged / "manifest.json"
        bronze_path = staged / "bronze.ndjson"
        shutil.copyfile(raw_path, staged_raw)
        shutil.copyfile(manifest_path, staged_manifest)
        if sha256_file(staged_raw) != manifest["identity"]["sha256"]:
            raise ValueError("Local event bytes changed after source release verification")
        if json.loads(staged_manifest.read_text(encoding="utf-8")) != manifest:
            raise ValueError("Local source manifest changed after release verification")
        _write_bronze_ndjson(bronze_path, events, manifest)
        total_bytes = (
            staged_raw.stat().st_size + staged_manifest.stat().st_size + bronze_path.stat().st_size
        )
        if total_bytes > max_upload_bytes:
            raise ValueError("Raw, manifest and bronze artifacts exceed max_upload_bytes")

        bucket = client.bucket(bucket_name)
        bucket.reload()
        if str(bucket.location).casefold() != location.casefold():
            raise ValueError(
                "Cloud Storage bucket location must exactly match the requested location"
            )
        iam_configuration = getattr(bucket, "iam_configuration", None)
        if not getattr(bucket, "versioning_enabled", False):
            raise ValueError("Cloud Storage object versioning must be enabled on the bucket")
        if (
            not getattr(iam_configuration, "uniform_bucket_level_access_enabled", False)
            or getattr(iam_configuration, "public_access_prevention", None) != "enforced"
        ):
            raise ValueError(
                "Cloud Storage bucket must use uniform access and enforced public access prevention"
            )
        raw = _upload_immutable_blob(
            bucket,
            f"{prefix}/events.jsonl",
            staged_raw,
            source_release_id=source_release_id,
            artifact_kind="raw-events-v1",
            row_count=len(events),
            content_type="application/x-ndjson",
        )
        manifest_object = _upload_immutable_blob(
            bucket,
            f"{prefix}/manifest.json",
            staged_manifest,
            source_release_id=source_release_id,
            artifact_kind="source-manifest-v1",
            row_count=len(events),
            content_type="application/json",
        )
        bronze = _upload_immutable_blob(
            bucket,
            f"{prefix}/bronze/events.ndjson",
            bronze_path,
            source_release_id=source_release_id,
            artifact_kind="bronze-events-v1",
            row_count=len(events),
            content_type="application/x-ndjson",
        )
    return {
        "source_release_id": source_release_id,
        "source_sha256": manifest["identity"]["sha256"],
        "source_manifest": manifest,
        "row_count": len(events),
        "location": str(bucket.location),
        "raw": raw,
        "manifest": manifest_object,
        "bronze": bronze,
    }


def _schema_field(bigquery: Any, name: str, field_type: str, mode: str) -> Any:
    return bigquery.SchemaField(name, field_type, mode=mode)


def _verify_destination_table(client: Any, destination: str, location: str) -> None:
    table = client.get_table(destination)
    if getattr(table, "table_type", None) != "TABLE":
        raise ValueError("BigQuery destination must be a native table")
    if str(table.location).casefold() != location.casefold():
        raise ValueError("BigQuery table location must exactly match the requested location")
    partitioning = getattr(table, "time_partitioning", None)
    if getattr(partitioning, "field", None) != "complete_through":
        raise ValueError("BigQuery destination must be partitioned by complete_through")
    clustering_fields = list(getattr(table, "clustering_fields", None) or [])
    if clustering_fields[:2] != ["source_release_id", "event_id"]:
        raise ValueError("BigQuery destination must cluster by source_release_id and event_id")
    actual = {field.name: field for field in table.schema}
    for name, field_type, mode in _BRONZE_SCHEMA:
        field = actual.get(name)
        if field is None:
            raise ValueError(f"BigQuery destination is missing required field: {name}")
        actual_type = _TYPE_ALIASES.get(
            str(field.field_type).upper(), str(field.field_type).upper()
        )
        if actual_type != field_type or str(field.mode).upper() != mode:
            raise ValueError(f"BigQuery destination field has incompatible type or mode: {name}")


def _query_summary(
    client: Any,
    destination: str,
    manifest: dict,
    location: str,
    max_query_bytes: int,
    bigquery: Any,
) -> dict[str, int]:
    identity = manifest["identity"]
    query = f"""
        SELECT
          COUNT(*) AS row_count,
          COUNT(DISTINCT TO_JSON_STRING(STRUCT(event_id, revision))) AS unique_keys,
          COUNT(DISTINCT event_sha256) AS unique_hashes,
          COUNTIF(
            source_id IS DISTINCT FROM @source_id OR
            source_sha256 IS DISTINCT FROM @source_sha256 OR
            schema_version IS DISTINCT FROM @schema_version OR
            complete_through IS DISTINCT FROM @complete_through OR
            source_type IS DISTINCT FROM 'SYNTHETIC'
          ) AS metadata_mismatches
        FROM `{destination}`
        WHERE source_release_id = @source_release_id
    """
    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "source_release_id", "STRING", manifest["source_release_id"]
            ),
            bigquery.ScalarQueryParameter("source_id", "STRING", identity["source_id"]),
            bigquery.ScalarQueryParameter("source_sha256", "STRING", identity["sha256"]),
            bigquery.ScalarQueryParameter("schema_version", "STRING", identity["schema_version"]),
            bigquery.ScalarQueryParameter("complete_through", "DATE", identity["complete_through"]),
        ],
        maximum_bytes_billed=max_query_bytes,
    )
    rows = list(client.query(query, job_config=config, location=location).result())
    if len(rows) != 1:
        raise ValueError("BigQuery reconciliation returned an invalid summary")
    row = rows[0]
    return {
        "row_count": int(row["row_count"] or 0),
        "unique_keys": int(row["unique_keys"] or 0),
        "unique_hashes": int(row["unique_hashes"] or 0),
        "metadata_mismatches": int(row["metadata_mismatches"] or 0),
    }


def _reconciliation_passed(summary: dict[str, int], expected_rows: int) -> bool:
    return (
        summary["row_count"] == expected_rows
        and summary["unique_keys"] == expected_rows
        and summary["unique_hashes"] == expected_rows
        and summary["metadata_mismatches"] == 0
    )


def load_event_release_to_bigquery(
    *,
    client: Any,
    bigquery: Any,
    bronze_uri: str,
    destination: str,
    manifest: dict,
    location: str,
    max_query_bytes: int,
) -> dict[str, Any]:
    """Load one GCS bronze artifact into an existing BigQuery table and reconcile it."""
    project_id, _, _ = _validated_destination(destination)
    if not _LOCATION.fullmatch(location):
        raise ValueError("An explicit BigQuery location is required")
    if type(max_query_bytes) is not int or max_query_bytes < 1:
        raise ValueError("max_query_bytes must be a positive integer")
    _validated_bronze_uri(bronze_uri, manifest, location)
    if client.project and client.project != project_id:
        raise ValueError("BigQuery client project must match the destination project")

    _verify_destination_table(client, destination, location)
    expected_rows = manifest["rows"]
    summary = _query_summary(client, destination, manifest, location, max_query_bytes, bigquery)
    if summary["row_count"]:
        if not _reconciliation_passed(summary, expected_rows):
            raise ValueError(
                "Existing BigQuery source release failed row or lineage reconciliation"
            )
        return {
            "destination": destination,
            "location": location,
            "source_release_id": manifest["source_release_id"],
            "row_count": expected_rows,
            "status": "ALREADY_PRESENT",
            "job_id": None,
        }

    job_identity = canonical_hash(
        {
            "source_release_id": manifest["source_release_id"],
            "destination": destination,
            "bronze_uri": bronze_uri,
        }
    )[:32]
    schema = [_schema_field(bigquery, *definition) for definition in _BRONZE_SCHEMA]
    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        create_disposition=bigquery.CreateDisposition.CREATE_NEVER,
        ignore_unknown_values=False,
        max_bad_records=0,
    )
    job = None
    for attempt in range(_MAX_LOAD_ATTEMPTS):
        job_id = f"retentionops_{job_identity}_a{attempt}"
        try:
            job = client.load_table_from_uri(
                bronze_uri,
                destination,
                job_id=job_id,
                location=location,
                job_config=config,
            )
        except Exception as exc:
            if _exception_code(exc) != 409:
                raise
            job = client.get_job(job_id, location=location)
        try:
            job.result()
            break
        except Exception as exc:
            if not getattr(job, "error_result", None):
                raise RuntimeError(
                    "BigQuery load status is unknown; reconcile before retrying"
                ) from exc
            if attempt == _MAX_LOAD_ATTEMPTS - 1:
                raise RuntimeError(
                    "BigQuery load failed after bounded deterministic attempts"
                ) from exc
            failed_summary = _query_summary(
                client, destination, manifest, location, max_query_bytes, bigquery
            )
            if failed_summary["row_count"]:
                if _reconciliation_passed(failed_summary, expected_rows):
                    return {
                        "destination": destination,
                        "location": location,
                        "source_release_id": manifest["source_release_id"],
                        "row_count": expected_rows,
                        "status": "ALREADY_PRESENT",
                        "job_id": getattr(job, "job_id", job_id),
                    }
                raise ValueError("Failed BigQuery job left unreconciled source rows") from exc
    else:
        raise RuntimeError("BigQuery load did not complete")

    output_rows = getattr(job, "output_rows", None)
    if output_rows is None or int(output_rows) != expected_rows:
        raise ValueError("BigQuery load output rows do not match the validated source manifest")
    summary = _query_summary(client, destination, manifest, location, max_query_bytes, bigquery)
    if not _reconciliation_passed(summary, expected_rows):
        raise ValueError("BigQuery load failed row or lineage reconciliation")
    return {
        "destination": destination,
        "location": location,
        "source_release_id": manifest["source_release_id"],
        "row_count": expected_rows,
        "status": "LOADED",
        "job_id": job.job_id,
    }


def publish_event_release_to_gcp(
    root: Path,
    source_release_id: str,
    *,
    storage_client: Any,
    bigquery_client: Any,
    bigquery: Any,
    bucket_name: str,
    destination: str,
    location: str,
    max_upload_bytes: int,
    max_query_bytes: int,
) -> dict[str, Any]:
    """Publish raw and bronze artifacts, then idempotently load the bronze release."""
    _validated_cloud_inputs(bucket_name, location)
    project_id, _, _ = _validated_destination(destination)
    if type(max_upload_bytes) is not int or max_upload_bytes < 1:
        raise ValueError("max_upload_bytes must be a positive integer")
    if type(max_query_bytes) is not int or max_query_bytes < 1:
        raise ValueError("max_query_bytes must be a positive integer")
    if getattr(bigquery_client, "project", None) not in (None, project_id):
        raise ValueError("BigQuery client project must match the destination project")
    _verify_destination_table(bigquery_client, destination, location)
    gcs_report = publish_event_release_to_gcs(
        root,
        source_release_id,
        client=storage_client,
        bucket_name=bucket_name,
        location=location,
        max_upload_bytes=max_upload_bytes,
    )
    manifest = gcs_report["source_manifest"]
    bq_report = load_event_release_to_bigquery(
        client=bigquery_client,
        bigquery=bigquery,
        bronze_uri=gcs_report["bronze"]["uri"],
        destination=destination,
        manifest=manifest,
        location=location,
        max_query_bytes=max_query_bytes,
    )
    gcs_report.pop("source_manifest", None)
    return {"gcs": gcs_report, "bigquery": bq_report}


def create_google_clients(destination: str) -> tuple[Any, Any, Any]:
    """Create ADC clients lazily so local-only installs need no Google libraries."""
    project_id, _, _ = _validated_destination(destination)
    try:
        from google.cloud import bigquery, storage
    except ImportError as exc:
        raise RuntimeError("Install the optional cloud SDK lock before using publish-gcp") from exc
    return storage.Client(project=project_id), bigquery.Client(project=project_id), bigquery
