"""Virtual memory swappiness optimizer.

/proc/sys/vm/swappiness is an integer between 0 and 200 (commonly 0-100 on older kernels).
It defines the Linux kernel memory manager's balance between reclaiming page cache
(file-backed pages like textures and binaries) vs swapping anonymous memory (heap/stack
memory allocated by processes).

Default swappiness is often 60. When set to 10, the kernel is strongly discouraged
from paging out process heap memory to disk unless absolutely necessary under heavy
memory pressure. This prevents gaming micro-stutters caused by major page faults
when frozen background game assets need to be paged back into physical RAM.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from backend.optimizer.base import Action, ProbeResult, is_dry_run, is_root

logger = logging.getLogger("gamemode.optimizer.swappiness")
SWAPPINESS_PATH = "/proc/sys/vm/swappiness"
TARGET_SWAPPINESS = 10


class SwappinessAction(Action):
    """Adjusts vm.swappiness to reduce anonymous page swapping during gameplay."""

    name = "swappiness"
    description = f"Lower vm.swappiness to {TARGET_SWAPPINESS} to protect game heap from swap stalls"

    def __init__(self, sys_path: str = SWAPPINESS_PATH) -> None:
        self.sys_path = sys_path

    def probe(self) -> ProbeResult:
        """Inspect /proc/sys/vm/swappiness presence and write permissions."""
        if is_dry_run():
            return {
                "supported": True,
                "reason": "Dry run mode active: simulated vm.swappiness tuning",
                "permission_denied": False,
            }

        if not os.path.exists(self.sys_path):
            return {
                "supported": False,
                "reason": f"System interface {self.sys_path} not found (Linux only)",
                "permission_denied": False,
            }

        if not os.access(self.sys_path, os.W_OK) and not is_root():
            return {
                "supported": False,
                "reason": f"Writing to {self.sys_path} requires root permissions (sudo)",
                "permission_denied": True,
            }

        return {
            "supported": True,
            "reason": f"{self.sys_path} is accessible and writable",
            "permission_denied": False,
        }

    def apply(self) -> dict[str, Any]:
        """Record current swappiness and write target value (10)."""
        if is_dry_run():
            logger.info(f"[DRY RUN] Simulating vm.swappiness -> {TARGET_SWAPPINESS}")
            return {
                "dry_run": True,
                "original_swappiness": 60,
                "target_swappiness": TARGET_SWAPPINESS,
            }

        if not os.path.exists(self.sys_path):
            raise FileNotFoundError(f"{self.sys_path} missing")

        with open(self.sys_path, "r", encoding="utf-8") as f:
            original_val = int(f.read().strip())

        with open(self.sys_path, "w", encoding="utf-8") as f:
            f.write(f"{TARGET_SWAPPINESS}\n")

        # Verify
        with open(self.sys_path, "r", encoding="utf-8") as f:
            new_val = int(f.read().strip())
            if new_val != TARGET_SWAPPINESS:
                logger.warning(f"Swappiness verification mismatch: expected {TARGET_SWAPPINESS}, got {new_val}")

        return {
            "dry_run": False,
            "original_swappiness": original_val,
            "target_swappiness": TARGET_SWAPPINESS,
        }

    def revert(self, undo_record: dict[str, Any]) -> None:
        """Restore previous swappiness value."""
        if undo_record.get("dry_run"):
            logger.info("[DRY RUN] Simulating vm.swappiness restoration")
            return

        original = undo_record.get("original_swappiness")
        if original is None:
            return

        try:
            with open(self.sys_path, "w", encoding="utf-8") as f:
                f.write(f"{original}\n")
            logger.info(f"Restored {self.sys_path} to {original}")
        except Exception as e:
            logger.error(f"Failed to restore {self.sys_path} to {original}: {e}")
