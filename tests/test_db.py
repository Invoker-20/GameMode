import os
import tempfile
import pytest
from backend.db import (
    init_db,
    insert_undo_log,
    update_undo_log_state,
    get_unreverted_undo_logs,
    insert_benchmark,
    update_benchmark_results,
    get_benchmarks,
    get_benchmark_by_id,
)


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_undo_log_workflow(test_db):
    log_id = insert_undo_log("swappiness", "pending", {"original": 60}, db_path=test_db)
    assert log_id > 0

    unreverted = get_unreverted_undo_logs(db_path=test_db)
    assert len(unreverted) == 1
    assert unreverted[0]["id"] == log_id
    assert unreverted[0]["state"] == "pending"
    assert unreverted[0]["undo_data"] == {"original": 60}

    # Mark as applied
    update_undo_log_state(log_id, "applied", db_path=test_db)
    unreverted = get_unreverted_undo_logs(db_path=test_db)
    assert len(unreverted) == 1
    assert unreverted[0]["state"] == "applied"

    # Mark as reverted
    update_undo_log_state(log_id, "reverted", db_path=test_db)
    unreverted = get_unreverted_undo_logs(db_path=test_db)
    assert len(unreverted) == 0


def test_benchmark_storage(test_db):
    b_id = insert_benchmark(
        label="Test Baseline",
        mode_enabled=False,
        params={"repetitions": 3, "synthetic_contention": False},
        db_path=test_db,
    )
    assert b_id > 0

    run = get_benchmark_by_id(b_id, db_path=test_db)
    assert run is not None
    assert run["label"] == "Test Baseline"
    assert run["mode_enabled"] is False
    assert run["results"] is None

    # Update with results
    results = {"latency": {"p50": 1.2, "p95": 2.5}}
    update_benchmark_results(b_id, results, db_path=test_db)

    run_updated = get_benchmark_by_id(b_id, db_path=test_db)
    assert run_updated["results"] == results

    runs = get_benchmarks(limit=10, db_path=test_db)
    assert len(runs) == 1
    assert runs[0]["id"] == b_id
