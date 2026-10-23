"""Base abstractions for system optimization actions."""

from __future__ import annotations

from abc import ABC, abstractmethod
import os
from typing import Any, TypedDict


def is_dry_run() -> bool:
    """Return True if GAMEMODE_DRY_RUN environment variable is set."""
    return os.environ.get("GAMEMODE_DRY_RUN", "").strip() in ("1", "true", "True", "yes")


def is_root() -> bool:
    """Check if the current process is running as root (EUID == 0)."""
    try:
        return hasattr(os, "geteuid") and os.geteuid() == 0
    except Exception:
        return False


class ProbeResult(TypedDict):
    supported: bool
    reason: str
    permission_denied: bool


class Action(ABC):
    """Abstract interface for reversible OS performance tuning actions."""

    name: str = "base_action"
    description: str = "Base optimization action"

    @abstractmethod
    def probe(self) -> ProbeResult:
        """Inspect hardware and permissions to check whether this action can run.

        Must never raise an unhandled exception. Return structured ProbeResult.
        """
        raise NotImplementedError

    @abstractmethod
    def apply(self) -> dict[str, Any]:
        """Apply the optimization.

        Before modifying system state, record all necessary original values in the
        returned undo record. Must be fully reversible by revert().
        """
        raise NotImplementedError

    @abstractmethod
    def revert(self, undo_record: dict[str, Any]) -> None:
        """Revert the optimization using the previously saved undo record.

        Must be idempotent and handle missing/changed state gracefully.
        """
        raise NotImplementedError
