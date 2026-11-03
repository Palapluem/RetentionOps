"""Reject forbidden tracked inputs/artifacts and obvious credential material before publish."""

import re
import subprocess
from pathlib import Path

FORBIDDEN = (
    "RetentionOps_Execution_Kit_2026-11-04",
    "data/",
    "artifacts/",
    "private/",
    ".venv/",
)
SECRET = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    rb"|gh[pousr]_[A-Za-z0-9]{30,}|AIza[A-Za-z0-9_-]{35}"
    rb'|"type"\s*:\s*"service_account"'
)


def main():
    paths = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
    failures = []
    for name in filter(None, paths):
        path = Path(name)
        if (
            name.startswith(FORBIDDEN)
            or path.suffix in (".sqlite", ".db", ".joblib", ".pem", ".key", ".parquet")
            or (path.name.startswith(".env") and path.name != ".env.example")
            or "service-account" in name
            or name.startswith("gha-creds-")
        ):
            failures.append(f"Forbidden tracked path: {name}")
        elif path.is_file() and SECRET.search(path.read_bytes()):
            failures.append(f"Potential credential in tracked file: {name}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Repository hygiene passed ({len(list(filter(None, paths)))} tracked paths).")


if __name__ == "__main__":
    main()
