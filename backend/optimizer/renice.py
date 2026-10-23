"""Background process priority (nice value) optimizer.

On Linux, the Completely Fair Scheduler (CFS) allocates CPU proportional to each
thread's nice level (ranging from -20 to +19, where lower = more CPU time). Normal
unprivileged processes run at nice 0.

By raising the nice value of background tasks (browsers, updaters, desktop indexers)
to +10, CFS reduces their CPU scheduling share relative to gaming threads.
Crucially, on Linux any process can become 'nicer' (raise nice value), but reducing
nice back to 0 requires the CAP_SYS_NICE capability or root permissions.

Safety guarantees:
1. Denylist: Never touches init (PID 1), kernel threads, display servers (Xorg/Wayland),
   compositors (mutter, kwin), audio servers (PipeWire, PulseAudio), or our own process tree.
2. Allowlist: Only deprioritizes explicitly recognized background services.
3. PID reuse prevention: Matches (pid, create_time) pairs. If a process terminated, its
   recycled PID will not be modified during revert.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import psutil

from backend.optimizer.base import Action, ProbeResult, is_dry_run, is_root

logger = logging.getLogger("gamemode.optimizer.renice")

TARGET_NICE_VALUE = 10

# Background processes suitable for deprioritization
DEFAULT_ALLOWLIST = {
    # Web browsers / electron apps running background helpers
    "chrome", "firefox", "brave", "opera", "discord", "slack", "spotify",
    # Desktop search indexers (known CPU/IO hogs)
    "tracker-miner-fs", "tracker-miner-rss", "baloo_file", "updatedb",
    # Background update checkers / downloaders
    "packagekitd", "dnf", "apt-check", "unattended-upgrades",
}

# Critical system services that must NEVER have their priority altered
DEFAULT_DENYLIST = {
    "systemd", "init", "kthreadd",
    # Display servers & compositors
    "xorg", "xwayland", "gnome-shell", "kwin_x11", "kwin_wayland",
    "mutter", "plasmashell", "hyprland", "sway", "weston",
    # Real-time audio pipelines
    "pipewire", "pipewire-pulse", "pulseaudio", "jackd",
}


class ReniceAction(Action):
    """Deprioritizes background non-gaming processes to reduce CPU contention."""

    name = "process_renice"
    description = f"Raise nice value of background processes to +{TARGET_NICE_VALUE} (leaving games and compositor intact)"

    def __init__(
        self,
        allowlist: set[str] | None = None,
        denylist: set[str] | None = None,
    ) -> None:
        self.allowlist = {name.lower() for name in (allowlist or DEFAULT_ALLOWLIST)}
        self.denylist = {name.lower() for name in (denylist or DEFAULT_DENYLIST)}

    def probe(self) -> ProbeResult:
        """Check if process renicing is supported and permitted."""
        if is_dry_run():
            return {
                "supported": True,
                "reason": "Dry run mode active: simulated background process renicing",
                "permission_denied": False,
            }

        # Restoring nice values back from +10 to 0 on Linux requires root / CAP_SYS_NICE
        if not is_root():
            return {
                "supported": False,
                "reason": "Restoring process nice values requires CAP_SYS_NICE or root permissions (sudo)",
                "permission_denied": True,
            }

        return {
            "supported": True,
            "reason": "CAP_SYS_NICE / root available; safe process renicing enabled",
            "permission_denied": False,
        }

    def _get_protected_pids(self) -> set[int]:
        """Collect PIDs of current process, its parents, and init."""
        protected: set[int] = {0, 1, 2}
        try:
            curr = psutil.Process(os.getpid())
            for p in curr.parents():
                protected.add(p.pid)
            protected.add(curr.pid)
        except Exception:
            pass
        return protected

    def _matches_allowlist(self, proc_name: str) -> bool:
        """Check if process name matches configured background candidate allowlist."""
        name_lower = proc_name.lower().replace(".exe", "")
        return any(cand in name_lower for cand in self.allowlist)

    def _matches_denylist(self, proc_name: str) -> bool:
        """Check if process matches critical denylist."""
        name_lower = proc_name.lower().replace(".exe", "")
        return any(deny in name_lower for deny in self.denylist)

    def apply(self) -> dict[str, Any]:
        """Find matching background processes, record original nice, and renice to +10."""
        if is_dry_run():
            logger.info(f"[DRY RUN] Simulating renice to +{TARGET_NICE_VALUE}")
            return {
                "dry_run": True,
                "reniced_processes": [
                    {"pid": 99999, "name": "simulated_browser", "create_time": 0.0, "original_nice": 0}
                ],
            }

        protected_pids = self._get_protected_pids()
        reniced_processes: list[dict[str, Any]] = []

        for proc in psutil.process_iter(["pid", "name", "create_time", "nice", "ppid"]):
            try:
                pid = proc.info["pid"]
                if pid in protected_pids:
                    continue

                # Skip kernel threads (PPID == 2 on Linux)
                if proc.info.get("ppid") == 2:
                    continue

                name = proc.info["name"] or ""
                if self._matches_denylist(name):
                    continue

                if not self._matches_allowlist(name):
                    continue

                raw_nice = proc.info["nice"]
                current_nice = int(raw_nice) if raw_nice is not None else 0
                create_time = proc.info["create_time"]

                # Only raise nice if currently at a higher priority (< TARGET_NICE_VALUE)
                if current_nice < TARGET_NICE_VALUE:
                    proc.nice(TARGET_NICE_VALUE)
                    reniced_processes.append(
                        {
                            "pid": pid,
                            "name": name,
                            "create_time": create_time,
                            "original_nice": current_nice,
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as e:
                logger.warning(f"Could not renice PID {proc.info.get('pid')}: {e}")
                continue

        return {
            "dry_run": False,
            "reniced_processes": reniced_processes,
        }

    def revert(self, undo_record: dict[str, Any]) -> None:
        """Restore original nice values for all processes recorded in undo record."""
        if undo_record.get("dry_run"):
            logger.info("[DRY RUN] Simulating renice restoration")
            return

        records = undo_record.get("reniced_processes", [])
        for entry in records:
            pid = entry["pid"]
            expected_create_time = entry["create_time"]
            original_nice = entry["original_nice"]

            try:
                proc = psutil.Process(pid)
                # Verify PID reuse: do not touch process if create_time differs
                if abs(proc.create_time() - expected_create_time) > 0.001:
                    logger.info(f"Skipping PID {pid} during revert: process was replaced")
                    continue

                proc.nice(original_nice)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as e:
                logger.error(f"Failed to restore nice for PID {pid}: {e}")
