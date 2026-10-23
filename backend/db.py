"""SQLite database layer for GameMode Lab write-ahead logs and benchmark results.

All database queries are designed to be invoked via asyncio.to_thread to prevent
blocking the FastAPI async event loop.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sqlite3
from typing import Any

DB_PATH = os.environ.get("GAMEMODE_DB_PATH", "gamemode.db")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Create a new SQLite connection with foreign keys and row factory enabled."""
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Initialize database tables for write-ahead undo logs and benchmark history."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS undo_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                created_at TEXT NOT NULL,
                state TEXT NOT NULL,
                undo_json TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS benchmark_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                label TEXT NOT NULL,
                mode_enabled INTEGER NOT NULL,
                params_json TEXT NOT NULL,
                results_json TEXT
            );
            """
        )
        conn.commit()


def insert_undo_log(
    action: str, state: str, undo_data: dict[str, Any], db_path: str = DB_PATH
) -> int:
    """Record write-ahead undo data in the database before applying an action."""
    now_iso = datetime.now(timezone.utc).isoformat()
    undo_json = json.dumps(undo_data)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO undo_log (action, created_at, state, undo_json)
            VALUES (?, ?, ?, ?);
            """,
            (action, now_iso, state, undo_json),
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_undo_log_state(
    log_id: int, new_state: str, db_path: str = DB_PATH
) -> None:
    """Update state of an undo log entry (e.g. pending -> applied -> reverted)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE undo_log SET state = ? WHERE id = ?;",
            (new_state, log_id),
        )
        conn.commit()


def get_unreverted_undo_logs(db_path: str = DB_PATH) -> list[dict[str, Any]]:
    """Retrieve all pending or applied actions that require reversal (recovery)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, action, created_at, state, undo_json
            FROM undo_log
            WHERE state IN ('pending', 'applied')
            ORDER BY id DESC;
            """
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "action": r["action"],
                "created_at": r["created_at"],
                "state": r["state"],
                "undo_data": json.loads(r["undo_json"]),
            }
            for r in rows
        ]


def get_latest_action_state(action: str, db_path: str = DB_PATH) -> str | None:
    """Get the most recent logged state for a specific action."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT state FROM undo_log
            WHERE action = ?
            ORDER BY id DESC LIMIT 1;
            """,
            (action,),
        )
        row = cursor.fetchone()
        return row["state"] if row else None


def insert_benchmark(
    label: str,
    mode_enabled: bool,
    params: dict[str, Any],
    db_path: str = DB_PATH,
) -> int:
    """Record the initiation of a benchmark run."""
    now_iso = datetime.now(timezone.utc).isoformat()
    params_json = json.dumps(params)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO benchmark_runs (started_at, label, mode_enabled, params_json, results_json)
            VALUES (?, ?, ?, ?, NULL);
            """,
            (now_iso, label, 1 if mode_enabled else 0, params_json),
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_benchmark_results(
    bench_id: int, results: dict[str, Any], db_path: str = DB_PATH
) -> None:
    """Store benchmark completion metrics."""
    results_json = json.dumps(results)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE benchmark_runs SET results_json = ? WHERE id = ?;",
            (results_json, bench_id),
        )
        conn.commit()


def get_benchmarks(limit: int = 50, db_path: str = DB_PATH) -> list[dict[str, Any]]:
    """Retrieve list of benchmark runs in descending order of run time."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, started_at, label, mode_enabled, params_json, results_json
            FROM benchmark_runs
            ORDER BY id DESC
            LIMIT ?;
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "started_at": r["started_at"],
                "label": r["label"],
                "mode_enabled": bool(r["mode_enabled"]),
                "params": json.loads(r["params_json"]),
                "results": json.loads(r["results_json"]) if r["results_json"] else None,
            }
            for r in rows
        ]


def get_benchmark_by_id(bench_id: int, db_path: str = DB_PATH) -> dict[str, Any] | None:
    """Retrieve details and metrics of a single benchmark run."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, started_at, label, mode_enabled, params_json, results_json
            FROM benchmark_runs
            WHERE id = ?;
            """,
            (bench_id,),
        )
        r = cursor.fetchone()
        if not r:
            return None
        return {
            "id": r["id"],
            "started_at": r["started_at"],
            "label": r["label"],
            "mode_enabled": bool(r["mode_enabled"]),
            "params": json.loads(r["params_json"]),
            "results": json.loads(r["results_json"]) if r["results_json"] else None,
        }
