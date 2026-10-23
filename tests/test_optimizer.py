import asyncio
import os
import tempfile
import pytest
from backend.db import init_db, get_unreverted_undo_logs, insert_undo_log
from backend.optimizer.base import is_dry_run
from backend.optimizer.governor import CpuGovernorAction
from backend.optimizer.swappiness import SwappinessAction
from backend.optimizer.renice import ReniceAction
from backend.optimizer.manager import OptimizationManager


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("GAMEMODE_DB_PATH", path)
    monkeypatch.setenv("GAMEMODE_DRY_RUN", "1")
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_dry_run_probe():
    assert is_dry_run() is True
    gov = CpuGovernorAction()
    probe_gov = gov.probe()
    assert probe_gov["supported"] is True
    assert "Dry run" in probe_gov["reason"]

    swap = SwappinessAction()
    probe_swap = swap.probe()
    assert probe_swap["supported"] is True

    renice = ReniceAction()
    probe_renice = renice.probe()
    assert probe_renice["supported"] is True


def test_dry_run_apply_and_revert():
    gov = CpuGovernorAction()
    record = gov.apply()
    assert record.get("dry_run") is True
    assert "governors" in record
    gov.revert(record)

    swap = SwappinessAction()
    record = swap.apply()
    assert record.get("dry_run") is True
    swap.revert(record)

    renice = ReniceAction()
    record = renice.apply()
    assert record.get("dry_run") is True
    renice.revert(record)


def test_manager_enable_and_disable(setup_test_env):
    async def _test():
        db_path = setup_test_env
        manager = OptimizationManager()
        assert not manager.is_mode_enabled

        results = await manager.enable_mode()
        assert manager.is_mode_enabled
        assert len(results) == 3
        for r in results:
            assert r["status"] == "applied"

        # Disable GameMode
        disable_results = await manager.disable_mode()
        assert not manager.is_mode_enabled
        assert len(disable_results) > 0
        for r in disable_results:
            assert r["status"] == "reverted"

        # Ensure no unreverted logs remain in DB
        unreverted = get_unreverted_undo_logs(db_path=db_path)
        assert len(unreverted) == 0

    asyncio.run(_test())


def test_manager_startup_recovery(setup_test_env, monkeypatch):
    async def _test():
        db_path = setup_test_env
        # Simulate a crash: insert an un-reverted applied log in DB
        insert_undo_log(
            "swappiness",
            "applied",
            {"dry_run": True, "original_swappiness": 60},
            db_path=db_path,
        )
        unreverted = get_unreverted_undo_logs(db_path=db_path)
        assert len(unreverted) == 1

        manager = OptimizationManager()
        recovered = await manager.recover_on_startup()
        assert recovered == 1

        # Verify DB has no more unreverted logs
        unreverted_after = get_unreverted_undo_logs(db_path=db_path)
        assert len(unreverted_after) == 0

    asyncio.run(_test())


def test_renice_pid_reuse_protection(monkeypatch):
    renice = ReniceAction()
    monkeypatch.delenv("GAMEMODE_DRY_RUN", raising=False)

    # Simulated undo record with an impossible create_time for our own PID
    my_pid = os.getpid()
    record = {
        "dry_run": False,
        "reniced_processes": [
            {
                "pid": my_pid,
                "name": "fake",
                "create_time": 9999999999.0,  # Far future timestamp mismatch
                "original_nice": 0,
            }
        ],
    }

    # Should not raise exception and should skip because timestamp mismatch
    renice.revert(record)

