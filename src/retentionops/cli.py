"""Run the synthetic demo explicitly; no training occurs when the API starts."""

import argparse
import json
from datetime import date
from pathlib import Path

from .data import DEFAULT_AS_OF, SEED
from .pipeline import run_event_pipeline, run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="RetentionOps synthetic local pipeline")
    parser.add_argument("command", choices=["all", "events"])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--customers", type=int, default=650)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--as-of", type=date.fromisoformat, default=DEFAULT_AS_OF)
    args = parser.parse_args()
    try:
        run = run_event_pipeline if args.command == "events" else run_pipeline
        result = run(args.root, args.customers, args.seed, args.as_of)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Pipeline failed; active publication unchanged: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
