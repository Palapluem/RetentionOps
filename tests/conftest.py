import pytest

from retentionops.data import generate_snapshots
from retentionops.pipeline import run_pipeline


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "snapshots.csv"
    generate_snapshots(path, customers=100)
    return path


@pytest.fixture
def publication(tmp_path):
    return tmp_path, run_pipeline(tmp_path, customers=150)
