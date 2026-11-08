"""Run the synthetic demo explicitly; no training occurs when the API starts."""

import argparse
import json
from datetime import date
from pathlib import Path

from .data import DEFAULT_AS_OF, SEED, sha256_file
from .events import generate_events, ingest_event_source
from .pipeline import run_event_pipeline, run_event_source_pipeline, run_pipeline
from .runs import complete_source_stage, tracked_run


def main() -> None:
    parser = argparse.ArgumentParser(description="RetentionOps synthetic local pipeline")
    parser.add_argument(
        "command", choices=["all", "events", "generate-events", "ingest-events", "run-events"]
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
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == "generate-events":
            if args.output is None:
                parser.error("generate-events requires --output")
            with tracked_run(root, "source-generation") as run_id:
                destination = args.output.expanduser().resolve()
                reserved = [
                    root / "artifacts",
                    *(root / "data" / name for name in ("events", "features", "raw", "staging")),
                ]
                if any(destination.is_relative_to(directory.resolve()) for directory in reserved):
                    raise ValueError(
                        "Output cannot be placed in managed artifacts or data releases"
                    )
                rows = generate_events(args.output, args.customers, args.seed)
                result = {
                    "output": str(args.output),
                    "rows": rows,
                    "sha256": sha256_file(args.output),
                }
                complete_source_stage(root, run_id, rows)
        elif args.command == "ingest-events":
            if args.input is None or args.source_id is None or args.complete_through is None:
                parser.error("ingest-events requires --input, --source-id, and --complete-through")
            with tracked_run(root, "source-intake") as run_id:
                result = ingest_event_source(
                    args.input, root, args.source_id, args.complete_through
                )
                complete_source_stage(root, run_id, result["rows"])
        elif args.command == "run-events":
            if args.source_release is None:
                parser.error("run-events requires --source-release")
            result = run_event_source_pipeline(root, args.source_release, args.seed, args.as_of)
        else:
            run = run_event_pipeline if args.command == "events" else run_pipeline
            result = run(root, args.customers, args.seed, args.as_of)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Pipeline failed; active publication unchanged: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
