#!/usr/bin/env bash
set -euo pipefail
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m pytest -q
python -m retentionops.cli all --customers 650
python scripts/check_repository.py
