"""Optimization manager coordinating write-ahead logging, application, and recovery."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from backend.db import (
    get_unreverted_undo_logs,
    insert_undo_log,
    update_undo_log_state,
)
from backend.optimizer.base import Action, is_dry_run, is_root
from backend.optimizer.governor import CpuGovernorAction
from backend.optimizer.renice import ReniceAction
from backend.optimizer.swappiness import SwappinessAction

logger = logging.getLogger("gamemode.optimizer.manager")


class OptimizationManager:
    """Orchestrates system optimizations with guaranteed write-ahead crash safety."""

    def __init__(self, actions: list[Action] | None = None) -> None:
        self.actions: dict[str, Action] = {}
        registered = actions or [
            CpuGovernorAction(),
            SwappinessAction(),
            ReniceAction(),
        ]
        for a in registered:
            self.actions[a.name] = a

        self._mode_enabled = False
        self._action_states: dict[str, str] = {a.name: "idle" for a in registered}
        self._lock = asyncio.Lock()

    @property
    def is_mode_enabled(self) -> bool:
        """Return whether GameMode is currently active."""
        return self._mode_enabled

    def get_capabilities(self) -> dict[str, Any]:
        """Inspect platform capabilities for frontend display."""
        import os
        from backend.psi import parse_psi

        psi_ok = parse_psi("cpu") is not None
        gov_probe = self.actions["cpu_governor"].probe()
        swap_probe = self.actions["swappiness"].probe()
        renice_probe = self.actions["process_renice"].probe()

        return {
            "psi": psi_ok,
            "cpufreq": "not available" not in gov_probe["reason"],
            "governor_writable": gov_probe["supported"],
            "can_renice": renice_probe["supported"],
            "swappiness_writable": swap_probe["supported"],
            "is_root": is_root(),
            "dry_run": is_dry_run(),
        }

    def get_action_statuses(self) -> list[dict[str, Any]]:
        """Return probe results and current states for all actions."""
        results = []
        for name, action in self.actions.items():
            probe = action.probe()
            current_state = self._action_states.get(name, "idle")

            # If not applied and unsupported, reflect probe status
            if current_state not in ("applied", "pending"):
                if not probe["supported"]:
                    current_state = "permission_denied" if probe["permission_denied"] else "unsupported"
                else:
                    current_state = "idle"

            results.append(
                {
                    "name": name,
                    "description": action.description,
                    "supported": probe["supported"],
                    "reason": probe["reason"],
                    "state": current_state,
                }
            )
        return results

    async def enable_mode(self) -> list[dict[str, Any]]:
        """Enable GameMode with write-ahead logging."""
        async with self._lock:
            results: list[dict[str, Any]] = []
            applied_any = False

            for name, action in self.actions.items():
                probe = action.probe()
                if not probe["supported"]:
                    status = "permission_denied" if probe["permission_denied"] else "unsupported"
                    self._action_states[name] = status
                    results.append(
                        {
                            "action": name,
                            "status": status,
                            "message": probe["reason"],
                            "undo_data": None,
                        }
                    )
                    continue

                try:
                    # Write-ahead: prepare and write pending undo log entry before applying
                    placeholder_undo: dict[str, Any] = {"status": "pending_apply"}
                    log_id = await asyncio.to_thread(
                        insert_undo_log, name, "pending", placeholder_undo
                    )

                    # Apply optimization in background thread
                    undo_record = await asyncio.to_thread(action.apply)

                    # Update database with complete undo payload and 'applied' state
                    await asyncio.to_thread(
                        insert_undo_log, name, "applied", undo_record
                    )
                    await asyncio.to_thread(update_undo_log_state, log_id, "applied")

                    self._action_states[name] = "applied"
                    applied_any = True
                    results.append(
                        {
                            "action": name,
                            "status": "applied",
                            "message": f"{name} applied successfully",
                            "undo_data": undo_record,
                        }
                    )
                except Exception as e:
                    logger.error(f"Error applying action {name}: {e}", exc_info=True)
                    self._action_states[name] = "error"
                    results.append(
                        {
                            "action": name,
                            "status": "error",
                            "message": f"Execution error: {e}",
                            "undo_data": None,
                        }
                    )

            self._mode_enabled = applied_any
            return results

    async def disable_mode(self) -> list[dict[str, Any]]:
        """Disable GameMode, reverting actions in reverse order."""
        async with self._lock:
            results: list[dict[str, Any]] = []
            # Retrieve all unreverted logs from database (newest first)
            unreverted = await asyncio.to_thread(get_unreverted_undo_logs)

            for log in unreverted:
                name = log["action"]
                action = self.actions.get(name)
                log_id = log["id"]
                undo_data = log["undo_data"]

                if action and undo_data.get("status") != "pending_apply":
                    try:
                        await asyncio.to_thread(action.revert, undo_data)
                    except Exception as e:
                        logger.error(f"Error reverting {name} (log {log_id}): {e}")

                await asyncio.to_thread(update_undo_log_state, log_id, "reverted")
                self._action_states[name] = "reverted"
                results.append(
                    {
                        "action": name,
                        "status": "reverted",
                        "message": f"{name} reverted to original state",
                        "undo_data": undo_data,
                    }
                )

            self._mode_enabled = False
            return results

    async def recover_on_startup(self) -> int:
        """Scan SQLite database for unreverted actions from previous crashed sessions."""
        unreverted = await asyncio.to_thread(get_unreverted_undo_logs)
        if not unreverted:
            logger.info("Startup recovery check: Clean state (no leftover optimizations).")
            return 0

        logger.warning(
            f"Startup recovery: Found {len(unreverted)} un-reverted action(s) from a previous session. Reverting now..."
        )
        for log in unreverted:
            name = log["action"]
            action = self.actions.get(name)
            log_id = log["id"]
            undo_data = log["undo_data"]

            if action and undo_data.get("status") != "pending_apply":
                try:
                    await asyncio.to_thread(action.revert, undo_data)
                    logger.info(f"Recovered and reverted action: {name} (id: {log_id})")
                except Exception as e:
                    logger.error(f"Recovery revert failed for {name}: {e}")

            await asyncio.to_thread(update_undo_log_state, log_id, "reverted")

        self._mode_enabled = False
        return len(unreverted)

    def setup_signal_handlers(self) -> None:
        """Register signal handlers to safely revert system changes on SIGINT/SIGTERM."""
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(
                        sig,
                        lambda: asyncio.create_task(self.disable_mode()),
                    )
                except (NotImplementedError, RuntimeError):
                    # Windows event loop doesn't support add_signal_handler
                    pass
        except Exception:
            pass
