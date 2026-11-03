"""Read-only tool/identity readiness; deliberately never print account/project identifiers."""

import json
import shutil
import subprocess


def read_gcloud(*args):
    return subprocess.run(
        ["gcloud", *args], capture_output=True, text=True, timeout=20, check=False
    )


def main():
    report = {
        "mode": "READ_ONLY",
        "cloud_changes": False,
        "tools": {
            name: bool(shutil.which(name))
            for name in ("python3.11", "git", "gh", "node", "npm", "docker", "gcloud", "bq")
        },
        "active_account": "NOT_VERIFIED",
        "selected_project": "NOT_VERIFIED",
        "region": "NOT_VERIFIED",
        "budget_alerts": "NOT_VERIFIED",
        "billing": "NOT_VERIFIED",
        "iam": "NOT_VERIFIED",
    }
    if report["tools"]["gcloud"]:
        try:
            account = read_gcloud(
                "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"
            )
            project = read_gcloud("config", "get-value", "project")
            report["active_account"] = bool(account.returncode == 0 and account.stdout.strip())
            report["selected_project"] = bool(
                project.returncode == 0 and project.stdout.strip() not in ("", "(unset)")
            )
        except (OSError, subprocess.TimeoutExpired):
            report["cli_error"] = "Identity check unavailable; inspect locally"
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
