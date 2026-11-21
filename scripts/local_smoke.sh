#!/usr/bin/env bash
set -euo pipefail
smoke_root="${RETENTIONOPS_ROOT:-.}"
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m pytest -q
python -m retentionops.cli all --root "$smoke_root" --customers 650
python -m retentionops.cli events --root "$smoke_root" --customers 650
python scripts/check_repository.py
