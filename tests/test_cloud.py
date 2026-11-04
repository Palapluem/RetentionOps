import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import retentionops.cloud as cloud_module
from retentionops.cloud import (
    _BRONZE_SCHEMA,
    _expected_bronze_rows,
    load_event_release_to_bigquery,
    publish_event_release_to_gcp,
    publish_event_release_to_gcs,
)
from retentionops.events import Event, ingest_event_source, load_event_source

LOCATION = "asia-southeast1"
DESTINATION = "retention-demo-123456.analytics.bronze_events"


class FakeHttpError(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket = bucket
        self.name = name
        self.metadata = None
        self.generation = None

    def upload_from_filename(self, filename, **kwargs):
        if kwargs["if_generation_match"] == 0 and self.name in self.bucket.objects:
            raise FakeHttpError(412)
        generation = str(len(self.bucket.objects) + 1)
        self.bucket.objects[self.name] = {
            "data": Path(filename).read_bytes(),
            "metadata": self.metadata,
            "generation": generation,
            "content_type": kwargs["content_type"],
        }
        self.generation = generation

    def reload(self):
        if self.name not in self.bucket.objects:
            raise FakeHttpError(404)
        stored = self.bucket.objects[self.name]
        self.metadata = stored["metadata"]
        self.generation = stored["generation"]

    def download_as_bytes(self):
        return self.bucket.objects[self.name]["data"]


class FakeBucket:
    def __init__(self, name, location=LOCATION):
        self.name = name
        self.location = location
        self.versioning_enabled = True
        self.iam_configuration = SimpleNamespace(
            uniform_bucket_level_access_enabled=True,
            public_access_prevention="enforced",
        )
        self.objects = {}

    def reload(self):
        return None

    def blob(self, name):
        return FakeBlob(self, name)


class FakeStorageClient:
    def __init__(self, bucket):
        self._bucket = bucket

    def bucket(self, name):
        assert name == self._bucket.name
        return self._bucket


def create_source_release(root):
    source = root / "incoming.jsonl"
    events = [
        Event(
            event_id="SYN-plan",
            customer_id="SYN-00001",
            kind="subscription",
            occurred_at=date(2026, 6, 20),
            available_at=date(2026, 6, 21),
            expiry_date=date(2026, 6, 30),
            started_at=date(2026, 1, 1),
            monthly_fee=149,
            auto_renew=1,
        ),
        Event(
            event_id="SYN-active",
            customer_id="SYN-00001",
            kind="activity",
            occurred_at=date(2026, 6, 15),
            available_at=date(2026, 6, 15),
        ),
    ]
    source.write_text("".join(f"{event.model_dump_json()}\n" for event in events))
    manifest = ingest_event_source(source, root, "demo-feed", date(2026, 11, 3))
    return manifest


class FakeSchemaField:
    def __init__(self, name, field_type, mode):
        self.name = name
        self.field_type = field_type
        self.mode = mode


class FakeField:
    def __init__(self, field_type):
        self.field_type = field_type
        self.mode = "REQUIRED"


class FakeQueryJobConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeLoadJobConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeScalarQueryParameter:
    def __init__(self, name, parameter_type, value):
        self.name = name
        self.type_ = parameter_type
        self.value = value


class FakeBigQuery:
    SchemaField = FakeSchemaField
    QueryJobConfig = FakeQueryJobConfig
    LoadJobConfig = FakeLoadJobConfig
    ScalarQueryParameter = FakeScalarQueryParameter
    SourceFormat = SimpleNamespace(NEWLINE_DELIMITED_JSON="NEWLINE_DELIMITED_JSON")
    WriteDisposition = SimpleNamespace(WRITE_APPEND="WRITE_APPEND")
    CreateDisposition = SimpleNamespace(CREATE_NEVER="CREATE_NEVER")


class FakeQueryJob:
    def __init__(self, rows):
        self.rows = rows

    def result(self):
        return self.rows


class FakeLoadJob:
    def __init__(self, client, job_id, *, error_result=None, output_rows=None):
        self.client = client
        self.job_id = job_id
        self.error_result = error_result
        self.output_rows = output_rows

    def result(self):
        if self.error_result:
            raise RuntimeError("simulated BigQuery job failure")
        rows = self.client.expected_rows
        self.client.summary = {
            "row_count": rows,
            "unique_keys": rows,
            "unique_hashes": rows,
            "metadata_mismatches": 0,
        }
        return self


class FakeBigQueryClient:
    project = "retention-demo-123456"

    def __init__(self, expected_rows, *, summary=None, conflict=False, failures=()):
        self.expected_rows = expected_rows
        self.summary = summary or {
            "row_count": 0,
            "unique_keys": 0,
            "unique_hashes": 0,
            "metadata_mismatches": 0,
        }
        self.conflict = conflict
        self.failures = list(failures)
        self.load_calls = []
        self.query_calls = []
        self.jobs = {}
        self.expected_event_rows = []
        self.row_overrides = {}
        fields = []
        for name, field_type, mode in _BRONZE_SCHEMA:
            field = FakeField(field_type)
            field.name = name
            field.mode = mode
            fields.append(field)
        self.table = SimpleNamespace(
            table_type="TABLE",
            location=LOCATION,
            schema=fields,
            time_partitioning=SimpleNamespace(field="complete_through"),
            clustering_fields=["source_release_id", "event_id"],
        )

    def get_table(self, destination):
        assert destination == DESTINATION
        return self.table

    def query(self, query, *, job_config, location):
        self.query_calls.append((query, job_config, location))
        row_count = self.summary["row_count"]
        rows = [dict(row) for row in self.expected_event_rows[:row_count]]
        if self.summary["unique_keys"] < row_count and len(rows) > 1:
            rows[-1] = dict(rows[0])
        if self.summary["unique_hashes"] < row_count and len(rows) > 1:
            rows[-1]["event_sha256"] = rows[0]["event_sha256"]
        if self.summary["metadata_mismatches"] and rows:
            rows[0]["source_id"] = "SYN-conflict"
        for index, overrides in self.row_overrides.items():
            if index < len(rows):
                rows[index].update(overrides)
        return FakeQueryJob(rows)

    def load_table_from_uri(self, uri, destination, *, job_id, location, job_config):
        self.load_calls.append((uri, destination, job_id, location, job_config))
        assert destination == DESTINATION
        if self.conflict:
            self.conflict = False
            self.jobs[job_id] = FakeLoadJob(
                self,
                job_id,
                output_rows=self.expected_rows,
            )
            raise FakeHttpError(409)
        failure = self.failures.pop(0) if self.failures else False
        job = FakeLoadJob(
            self,
            job_id,
            error_result={"reason": "backendError"} if failure else None,
            output_rows=self.expected_rows,
        )
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id, *, location):
        assert location == LOCATION
        return self.jobs[job_id]


def load_release(client, manifest, *, root, bigquery=FakeBigQuery, bronze_uri=None):
    events, loaded_manifest = load_event_source(root, manifest["source_release_id"])
    assert loaded_manifest == manifest
    client.expected_event_rows = _expected_bronze_rows(events, manifest)
    return load_event_release_to_bigquery(
        client=client,
        bigquery=bigquery,
        bronze_uri=bronze_uri
        or (
            "gs://retentionops-demo/retentionops/"
            f"{manifest['identity']['source_id']}/{manifest['source_release_id']}/"
            "bronze/events.ndjson"
        ),
        destination=DESTINATION,
        manifest=manifest,
        expected_events=events,
        location=LOCATION,
        max_query_bytes=50_000_000,
    )


def test_gcs_publishes_exact_raw_source_and_replay_is_idempotent(tmp_path):
    manifest = create_source_release(tmp_path)
    bucket = FakeBucket("retentionops-demo")
    client = FakeStorageClient(bucket)

    first = publish_event_release_to_gcs(
        tmp_path,
        manifest["source_release_id"],
        client=client,
        bucket_name=bucket.name,
        location=LOCATION,
        max_upload_bytes=10_000_000,
    )
    second = publish_event_release_to_gcs(
        tmp_path,
        manifest["source_release_id"],
        client=client,
        bucket_name=bucket.name,
        location=LOCATION,
        max_upload_bytes=10_000_000,
    )

    raw_key = first["raw"]["uri"].split(bucket.name + "/", maxsplit=1)[1]
    expected_raw = (
        tmp_path / "data/events" / manifest["source_release_id"] / "events.jsonl"
    ).read_bytes()
    assert first["raw"]["status"] == "UPLOADED"
    assert second["raw"]["status"] == "ALREADY_PRESENT"
    assert first["raw"]["generation"] == second["raw"]["generation"]
    assert bucket.objects[raw_key]["data"] == expected_raw
    assert first["bronze"]["uri"].endswith("/bronze/events.ndjson")
    assert len(bucket.objects) == 3


def test_gcs_replay_rejects_object_with_changed_bytes(tmp_path):
    manifest = create_source_release(tmp_path)
    bucket = FakeBucket("retentionops-demo")
    client = FakeStorageClient(bucket)
    first = publish_event_release_to_gcs(
        tmp_path,
        manifest["source_release_id"],
        client=client,
        bucket_name=bucket.name,
        location=LOCATION,
        max_upload_bytes=10_000_000,
    )
    raw_key = first["raw"]["uri"].split(bucket.name + "/", maxsplit=1)[1]
    bucket.objects[raw_key]["data"] = b"tampered\n"

    with pytest.raises(ValueError, match="checksum conflicts"):
        publish_event_release_to_gcs(
            tmp_path,
            manifest["source_release_id"],
            client=client,
            bucket_name=bucket.name,
            location=LOCATION,
            max_upload_bytes=10_000_000,
        )


def test_gcs_replay_rejects_object_with_conflicting_release_metadata(tmp_path):
    manifest = create_source_release(tmp_path)
    bucket = FakeBucket("retentionops-demo")
    client = FakeStorageClient(bucket)
    first = publish_event_release_to_gcs(
        tmp_path,
        manifest["source_release_id"],
        client=client,
        bucket_name=bucket.name,
        location=LOCATION,
        max_upload_bytes=10_000_000,
    )
    raw_key = first["raw"]["uri"].split(bucket.name + "/", maxsplit=1)[1]
    bucket.objects[raw_key]["metadata"]["source_release_id"] = "conflicting-release"

    with pytest.raises(ValueError, match="metadata conflicts"):
        publish_event_release_to_gcs(
            tmp_path,
            manifest["source_release_id"],
            client=client,
            bucket_name=bucket.name,
            location=LOCATION,
            max_upload_bytes=10_000_000,
        )


def test_gcs_stages_and_rechecks_raw_bytes_after_source_validation(tmp_path, monkeypatch):
    manifest = create_source_release(tmp_path)
    bucket = FakeBucket("retentionops-demo")
    original_loader = cloud_module.load_event_source
    raw_path = tmp_path / "data/events" / manifest["source_release_id"] / "events.jsonl"

    def validate_then_change(root, source_release_id):
        events, loaded_manifest = original_loader(root, source_release_id)
        raw_path.write_bytes(b"changed after validation\n")
        return events, loaded_manifest

    monkeypatch.setattr(cloud_module, "load_event_source", validate_then_change)

    with pytest.raises(ValueError, match="changed after source release verification"):
        publish_event_release_to_gcs(
            tmp_path,
            manifest["source_release_id"],
            client=FakeStorageClient(bucket),
            bucket_name=bucket.name,
            location=LOCATION,
            max_upload_bytes=10_000_000,
        )
    assert bucket.objects == {}


@pytest.mark.parametrize(
    ("setting", "message"),
    [
        ("versioning", "versioning must be enabled"),
        ("uniform_access", "uniform access"),
        ("public_access", "public access prevention"),
    ],
)
def test_gcs_rejects_unprotected_bucket_before_upload(tmp_path, setting, message):
    manifest = create_source_release(tmp_path)
    bucket = FakeBucket("retentionops-demo")
    if setting == "versioning":
        bucket.versioning_enabled = False
    elif setting == "uniform_access":
        bucket.iam_configuration.uniform_bucket_level_access_enabled = False
    else:
        bucket.iam_configuration.public_access_prevention = "inherited"

    with pytest.raises(ValueError, match=message):
        publish_event_release_to_gcs(
            tmp_path,
            manifest["source_release_id"],
            client=FakeStorageClient(bucket),
            bucket_name=bucket.name,
            location=LOCATION,
            max_upload_bytes=10_000_000,
        )
    assert bucket.objects == {}


def test_gcs_enforces_explicit_upload_cap_before_writing_objects(tmp_path):
    manifest = create_source_release(tmp_path)
    bucket = FakeBucket("retentionops-demo")

    with pytest.raises(ValueError, match="Raw source exceeds max_upload_bytes"):
        publish_event_release_to_gcs(
            tmp_path,
            manifest["source_release_id"],
            client=FakeStorageClient(bucket),
            bucket_name=bucket.name,
            location=LOCATION,
            max_upload_bytes=1,
        )
    assert bucket.objects == {}


def test_bronze_payload_carries_lineage_and_canonical_event_hash(tmp_path):
    manifest = create_source_release(tmp_path)
    bucket = FakeBucket("retentionops-demo")
    report = publish_event_release_to_gcs(
        tmp_path,
        manifest["source_release_id"],
        client=FakeStorageClient(bucket),
        bucket_name=bucket.name,
        location=LOCATION,
        max_upload_bytes=10_000_000,
    )
    bronze_key = report["bronze"]["uri"].split(bucket.name + "/", maxsplit=1)[1]
    rows = [json.loads(line) for line in bucket.objects[bronze_key]["data"].splitlines()]
    assert len(rows) == manifest["rows"]
    assert {row["source_release_id"] for row in rows} == {manifest["source_release_id"]}
    assert {row["source_sha256"] for row in rows} == {manifest["sha256"]}
    assert all(len(row["event_sha256"]) == 64 for row in rows)


def test_bigquery_load_is_create_never_bounded_and_reconciled(tmp_path):
    manifest = create_source_release(tmp_path)
    client = FakeBigQueryClient(manifest["rows"])

    report = load_release(client, manifest, root=tmp_path)

    assert report["status"] == "LOADED"
    assert report["row_count"] == manifest["rows"]
    config = client.load_calls[0][4]
    assert config.create_disposition == "CREATE_NEVER"
    assert config.write_disposition == "WRITE_APPEND"
    assert config.max_bad_records == 0
    assert len(config.schema) == len(_BRONZE_SCHEMA)
    assert client.query_calls[-1][1].maximum_bytes_billed == 50_000_000
    assert "source_release_id = @source_release_id" in client.query_calls[-1][0]


def test_current_google_bigquery_sdk_accepts_adapter_config_without_credentials(tmp_path):
    bigquery = pytest.importorskip("google.cloud.bigquery")
    manifest = create_source_release(tmp_path)
    client = FakeBigQueryClient(manifest["rows"])

    report = load_release(client, manifest, root=tmp_path, bigquery=bigquery)

    assert report["status"] == "LOADED"
    config = client.load_calls[0][4]
    assert isinstance(config, bigquery.LoadJobConfig)
    assert config.source_format == bigquery.SourceFormat.NEWLINE_DELIMITED_JSON
    assert config.create_disposition == bigquery.CreateDisposition.CREATE_NEVER
    assert len(config.schema) == len(_BRONZE_SCHEMA)


def test_explicit_gcp_publish_connects_verified_gcs_to_bigquery(tmp_path):
    manifest = create_source_release(tmp_path)
    bucket = FakeBucket("retentionops-demo")
    bigquery_client = FakeBigQueryClient(manifest["rows"])
    events, _ = load_event_source(tmp_path, manifest["source_release_id"])
    bigquery_client.expected_event_rows = _expected_bronze_rows(events, manifest)

    report = publish_event_release_to_gcp(
        tmp_path,
        manifest["source_release_id"],
        storage_client=FakeStorageClient(bucket),
        bigquery_client=bigquery_client,
        bigquery=FakeBigQuery,
        bucket_name=bucket.name,
        destination=DESTINATION,
        location=LOCATION,
        max_upload_bytes=10_000_000,
        max_query_bytes=50_000_000,
    )

    assert report["gcs"]["row_count"] == manifest["rows"]
    assert report["bigquery"]["status"] == "LOADED"
    assert len(bucket.objects) == 3
    assert bigquery_client.summary["row_count"] == manifest["rows"]


def test_bigquery_replay_skips_a_reconciled_release(tmp_path):
    manifest = create_source_release(tmp_path)
    rows = manifest["rows"]
    client = FakeBigQueryClient(
        rows,
        summary={
            "row_count": rows,
            "unique_keys": rows,
            "unique_hashes": rows,
            "metadata_mismatches": 0,
        },
    )

    report = load_release(client, manifest, root=tmp_path)

    assert report["status"] == "ALREADY_PRESENT"
    assert report["row_count"] == rows
    assert client.load_calls == []


def test_bigquery_rejects_partial_or_duplicate_release_before_append(tmp_path):
    manifest = create_source_release(tmp_path)
    rows = manifest["rows"]
    client = FakeBigQueryClient(
        rows,
        summary={
            "row_count": rows,
            "unique_keys": rows - 1,
            "unique_hashes": rows,
            "metadata_mismatches": 0,
        },
    )

    with pytest.raises(ValueError, match="failed row or lineage reconciliation"):
        load_release(client, manifest, root=tmp_path)
    assert client.load_calls == []


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("row_count", "short"),
        ("unique_hashes", "short"),
        ("metadata_mismatches", "present"),
    ],
)
def test_bigquery_rejects_row_hash_or_lineage_mismatch_before_append(
    tmp_path, field, invalid_value
):
    manifest = create_source_release(tmp_path)
    rows = manifest["rows"]
    summary = {
        "row_count": rows,
        "unique_keys": rows,
        "unique_hashes": rows,
        "metadata_mismatches": 0,
    }
    summary[field] = rows - 1 if invalid_value == "short" else 1
    client = FakeBigQueryClient(rows, summary=summary)

    with pytest.raises(ValueError, match="failed row or lineage reconciliation"):
        load_release(client, manifest, root=tmp_path)
    assert client.load_calls == []


def test_bigquery_rejects_changed_row_fields_even_when_hash_is_preserved(tmp_path):
    manifest = create_source_release(tmp_path)
    rows = manifest["rows"]
    client = FakeBigQueryClient(
        rows,
        summary={
            "row_count": rows,
            "unique_keys": rows,
            "unique_hashes": rows,
            "metadata_mismatches": 0,
        },
    )
    client.row_overrides = {0: {"customer_id": "SYN-99999"}}

    with pytest.raises(ValueError, match="failed row or lineage reconciliation"):
        load_release(client, manifest, root=tmp_path)
    assert client.load_calls == []


def test_bigquery_rejects_wildcard_or_mismatched_release_uri(tmp_path):
    manifest = create_source_release(tmp_path)
    client = FakeBigQueryClient(manifest["rows"])

    with pytest.raises(ValueError, match="must target this release's bronze artifact"):
        load_release(
            client,
            manifest,
            root=tmp_path,
            bronze_uri=(
                "gs://retentionops-demo/retentionops/"
                f"{manifest['identity']['source_id']}/{manifest['source_release_id']}/"
                "bronze/*.ndjson"
            ),
        )
    assert client.query_calls == []
    assert client.load_calls == []


def test_bigquery_recovers_a_duplicate_job_submission(tmp_path):
    manifest = create_source_release(tmp_path)
    client = FakeBigQueryClient(manifest["rows"], conflict=True)

    report = load_release(client, manifest, root=tmp_path)

    assert report["status"] == "LOADED"
    assert len(client.load_calls) == 1
    assert client.load_calls[0][2] == report["job_id"]


def test_bigquery_retries_a_confirmed_failed_job_with_predictable_id(tmp_path):
    manifest = create_source_release(tmp_path)
    client = FakeBigQueryClient(manifest["rows"], failures=[True, False])

    report = load_release(client, manifest, root=tmp_path)

    assert report["status"] == "LOADED"
    assert len(client.load_calls) == 2
    assert client.load_calls[0][2].endswith("_a0")
    assert client.load_calls[1][2].endswith("_a1")


def test_bigquery_rejects_unknown_load_status_instead_of_restarting(tmp_path):
    manifest = create_source_release(tmp_path)
    client = FakeBigQueryClient(manifest["rows"])

    def unknown_status(*args, **kwargs):
        job_id = kwargs["job_id"]
        job = FakeLoadJob(client, job_id, output_rows=manifest["rows"])
        job.result = lambda: (_ for _ in ()).throw(RuntimeError("transport lost"))
        return job

    client.load_table_from_uri = unknown_status
    with pytest.raises(RuntimeError, match="status is unknown"):
        load_release(client, manifest, root=tmp_path)
    assert len(client.query_calls) == 1


def test_bigquery_requires_partitioned_and_clustered_target(tmp_path):
    manifest = create_source_release(tmp_path)
    client = FakeBigQueryClient(manifest["rows"])
    client.table.time_partitioning = None

    with pytest.raises(ValueError, match="partitioned by complete_through"):
        load_release(client, manifest, root=tmp_path)
    assert client.query_calls == []


def test_missing_bigquery_destination_fails_before_gcs_upload(tmp_path):
    manifest = create_source_release(tmp_path)
    bucket = FakeBucket("retentionops-demo")
    bigquery_client = FakeBigQueryClient(manifest["rows"])

    def missing_table(destination):
        raise FakeHttpError(404)

    bigquery_client.get_table = missing_table
    with pytest.raises(FakeHttpError):
        publish_event_release_to_gcp(
            tmp_path,
            manifest["source_release_id"],
            storage_client=FakeStorageClient(bucket),
            bigquery_client=bigquery_client,
            bigquery=FakeBigQuery,
            bucket_name=bucket.name,
            destination=DESTINATION,
            location=LOCATION,
            max_upload_bytes=10_000_000,
            max_query_bytes=50_000_000,
        )
    assert bucket.objects == {}


def test_bronze_contract_matches_adapter_schema():
    contract = json.loads(
        (Path(__file__).parents[1] / "contracts/bigquery_bronze_events.json").read_text()
    )
    expected = [
        {"name": name, "type": field_type, "mode": mode}
        for name, field_type, mode in _BRONZE_SCHEMA
    ]
    assert contract["schema_version"] == "event-source-bronze-v1"
    assert contract["partition_field"] == "complete_through"
    assert contract["cluster_fields"] == ["source_release_id", "event_id"]
    assert contract["fields"] == expected
