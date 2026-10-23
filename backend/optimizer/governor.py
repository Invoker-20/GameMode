"""CPU frequency scaling governor optimizer.

On Linux, CPU frequency is managed by scaling governors (e.g., powersave, schedutil,
performance). Under the default 'powersave' or 'schedutil' governors, clock rates drop
rapidly when idle and ramp up only after thread demand increases. This latency in
frequency scaling (P-state transitions) causes micro-stutters during sudden game bursts.
Setting the governor to 'performance' instructs the cpufreq driver (intel_pstate,
amd-pstate, or acpi-cpufreq) to maintain maximum rated operating frequency.
"""

from __future__ import annotations

import glob
import logging
import os
from typing import Any

from backend.optimizer.base import Action, ProbeResult, is_dry_run, is_root

logger = logging.getLogger("gamemode.optimizer.governor")
CPU_SYSFS_PATTERN = "/sys/devices/system/cpu/cpu[0-9]*/cpufreq"


class CpuGovernorAction(Action):
    """Switches CPU frequency scaling governors to 'performance'."""

    name = "cpu_governor"
    description = "Switch CPU scaling governor to 'performance' to avoid frequency scaling latency"

    def __init__(self, sysfs_pattern: str = CPU_SYSFS_PATTERN) -> None:
        self.sysfs_pattern = sysfs_pattern

    def probe(self) -> ProbeResult:
        """Inspect cpufreq sysfs files and permissions."""
        if is_dry_run():
            return {
                "supported": True,
                "reason": "Dry run mode active: simulated CPU governor control",
                "permission_denied": False,
            }

        cpu_dirs = sorted(glob.glob(self.sysfs_pattern))
        if not cpu_dirs:
            return {
                "supported": False,
                "reason": "CPU frequency scaling (cpufreq) sysfs interface not available (hardware or driver dependent)",
                "permission_denied": False,
            }

        # Check if 'performance' is in scaling_available_governors
        avail_file = os.path.join(cpu_dirs[0], "scaling_available_governors")
        try:
            if not os.path.isfile(avail_file):
                return {
                    "supported": False,
                    "reason": "scaling_available_governors file missing; driver may use fixed energy_performance_preference",
                    "permission_denied": False,
                }
            with open(avail_file, "r", encoding="utf-8") as f:
                available = f.read().split()

            if "performance" not in available:
                return {
                    "supported": False,
                    "reason": f"'performance' governor not in available governors: {available}",
                    "permission_denied": False,
                }
        except Exception as e:
            return {
                "supported": False,
                "reason": f"Failed reading cpufreq capabilities: {e}",
                "permission_denied": False,
            }

        # Check write permissions
        gov_file = os.path.join(cpu_dirs[0], "scaling_governor")
        if not os.access(gov_file, os.W_OK) and not is_root():
            return {
                "supported": False,
                "reason": "Modifying /sys cpufreq governor requires root permissions (sudo)",
                "permission_denied": True,
            }

        return {
            "supported": True,
            "reason": f"cpufreq active across {len(cpu_dirs)} core(s); 'performance' governor available",
            "permission_denied": False,
        }

    def apply(self) -> dict[str, Any]:
        """Record original governors per core and write 'performance'."""
        if is_dry_run():
            logger.info("[DRY RUN] Simulating CPU governor -> performance")
            return {
                "dry_run": True,
                "governors": {"cpu0": "powersave", "cpu1": "powersave"},
            }

        cpu_dirs = sorted(glob.glob(self.sysfs_pattern))
        if not cpu_dirs:
            raise RuntimeError("cpufreq sysfs nodes missing during apply")

        original_governors: dict[str, str] = {}

        # 1. Read current governors
        for cpu_dir in cpu_dirs:
            cpu_name = os.path.basename(os.path.dirname(cpu_dir))
            gov_path = os.path.join(cpu_dir, "scaling_governor")
            with open(gov_path, "r", encoding="utf-8") as f:
                original_governors[cpu_name] = f.read().strip()

        # 2. Write 'performance' and verify
        for cpu_dir in cpu_dirs:
            cpu_name = os.path.basename(os.path.dirname(cpu_dir))
            gov_path = os.path.join(cpu_dir, "scaling_governor")
            with open(gov_path, "w", encoding="utf-8") as f:
                f.write("performance\n")

            with open(gov_path, "r", encoding="utf-8") as f:
                new_val = f.read().strip()
                if new_val != "performance":
                    logger.warning(f"Governor verification mismatch for {cpu_name}: {new_val}")

        return {
            "dry_run": False,
            "governors": original_governors,
        }

    def revert(self, undo_record: dict[str, Any]) -> None:
        """Restore original governor values per core."""
        if undo_record.get("dry_run"):
            logger.info("[DRY RUN] Simulating CPU governor restoration")
            return

        original = undo_record.get("governors", {})
        cpu_dirs = sorted(glob.glob(self.sysfs_pattern))

        for cpu_dir in cpu_dirs:
            cpu_name = os.path.basename(os.path.dirname(cpu_dir))
            target_gov = original.get(cpu_name)
            if not target_gov:
                continue

            gov_path = os.path.join(cpu_dir, "scaling_governor")
            try:
                with open(gov_path, "w", encoding="utf-8") as f:
                    f.write(f"{target_gov}\n")
            except Exception as e:
                logger.error(f"Failed to restore governor for {cpu_name} to {target_gov}: {e}")
