"""Run the synthetic demo explicitly; no training occurs when the API starts."""

import argparse
import json
from datetime import date
from pathlib import Path

from .data import DEFAULT_AS_OF, SEED, sha256_file
from .events import generate_events, ingest_event_source
from .pipeline import run_event_pipeline, run_event_source_pipeline, run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="RetentionOps synthetic local pipeline")
    parser.add_argument(
        "command",
        choices=[
            "all",
            "events",
            "generate-events",
            "ingest-events",
            "run-events",
            "publish-gcp",
        ],
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--customers", type=int, default=650)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--as-of", type=date.fromisoformat, default=DEFAULT_AS_OF)
    parser.add_argument("--input", type=Path, help="Synthetic event JSONL file to ingest")
    parser.add_argument("--output", type=Path, help="Output path for generate-events")
    parser.add_argument("--source-id", help="Stable source identity for an ingested event file")
    parser.add_argument("--complete-through", type=date.fromisoformat)
    parser.add_argument("--source-release", help="Previously ingested event release ID")
    parser.add_argument("--bucket", help="Existing private GCS bucket")
    parser.add_argument("--table", help="Existing BigQuery project.dataset.table target")
    parser.add_argument("--location", help="Explicit co-located GCS and BigQuery location")
    parser.add_argument("--max-upload-bytes", type=int, help="Maximum total bytes uploaded to GCS")
    parser.add_argument(
        "--max-query-bytes", type=int, help="Maximum bytes billed per reconciliation query"
    )
    args = parser.parse_args()
    try:
        if args.command == "publish-gcp":
            required = {
                "--source-release": args.source_release,
                "--bucket": args.bucket,
                "--table": args.table,
                "--location": args.location,
                "--max-upload-bytes": args.max_upload_bytes,
                "--max-query-bytes": args.max_query_bytes,
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                parser.error(f"publish-gcp requires {', '.join(missing)}")
            if args.max_upload_bytes < 1 or args.max_query_bytes < 1:
                parser.error("publish-gcp byte limits must be positive integers")
            from .cloud import create_google_clients, publish_event_release_to_gcp

            storage_client, bigquery_client, bigquery = create_google_clients(args.table)
            result = publish_event_release_to_gcp(
                args.root,
                args.source_release,
                storage_client=storage_client,
                bigquery_client=bigquery_client,
                bigquery=bigquery,
                bucket_name=args.bucket,
                destination=args.table,
                location=args.location,
                max_upload_bytes=args.max_upload_bytes,
                max_query_bytes=args.max_query_bytes,
            )
        elif args.command == "generate-events":
            if args.output is None:
                parser.error("generate-events requires --output")
            rows = generate_events(args.output, args.customers, args.seed)
            result = {"output": str(args.output), "rows": rows, "sha256": sha256_file(args.output)}
        elif args.command == "ingest-events":
            if args.input is None or args.source_id is None or args.complete_through is None:
                parser.error("ingest-events requires --input, --source-id, and --complete-through")
            result = ingest_event_source(
                args.input, args.root, args.source_id, args.complete_through
            )
        elif args.command == "run-events":
            if args.source_release is None:
                parser.error("run-events requires --source-release")
            result = run_event_source_pipeline(
                args.root, args.source_release, args.seed, args.as_of
            )
        else:
            run = run_event_pipeline if args.command == "events" else run_pipeline
            result = run(args.root, args.customers, args.seed, args.as_of)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"RetentionOps command failed; inspect source and cloud job status: {exc}\n")
    except Exception as exc:
        parser.exit(1, f"RetentionOps command failed; inspect cloud logs if applicable: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
