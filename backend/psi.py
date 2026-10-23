"""Linux Pressure Stall Information (PSI) parser and helpers.

PSI was introduced in Linux Kernel 4.20 to provide accurate metrics for resource
contention (CPU, Memory, I/O) before the system enters severe thrashing or OOM states.
Unlike traditional CPU utilization or load average (which conflate productive work with
waiting), PSI explicitly quantifies how much processing capacity is lost due to delays:

- 'some': At least one task is stalled waiting for the hardware resource while runnable.
  For CPU, only 'some' exists because if any task is executing, CPU throughput is progressing.
- 'full': ALL non-idle tasks are simultaneously stalled waiting for the resource (e.g. all
  tasks blocked on swap I/O or page faulting). In this state, CPU cycles are completely wasted.
- avg10, avg60, avg300: 10s, 60s, and 300s decaying averages of percentage stall time.
- total: Cumulative time in microseconds (us) tasks spent stalled.
"""

from __future__ import annotations

import os
from typing import TypedDict


class PsiMetrics(TypedDict):
    avg10: float
    avg60: float
    avg300: float
    total: int


class PsiRecord(TypedDict):
    some: PsiMetrics
    full: PsiMetrics | None


def _parse_psi_line(line: str) -> tuple[str, PsiMetrics] | None:
    """Parse a single PSI line such as:
    'some avg10=0.00 avg60=0.00 avg300=0.00 total=12345'
    """
    parts = line.strip().split()
    if not parts or parts[0] not in ("some", "full"):
        return None

    line_type = parts[0]
    metrics: dict[str, float | int] = {}

    for part in parts[1:]:
        if "=" not in part:
            continue
        key, val = part.split("=", 1)
        try:
            if key in ("avg10", "avg60", "avg300"):
                metrics[key] = float(val)
            elif key == "total":
                metrics[key] = int(val)
        except ValueError:
            return None

    if {"avg10", "avg60", "avg300", "total"}.issubset(metrics.keys()):
        return line_type, PsiMetrics(
            avg10=float(metrics["avg10"]),
            avg60=float(metrics["avg60"]),
            avg300=float(metrics["avg300"]),
            total=int(metrics["total"]),
        )
    return None


def parse_psi(resource: str, pressure_dir: str = "/proc/pressure") -> PsiRecord | None:
    """Read and parse /proc/pressure/<resource> where resource is 'cpu', 'memory', or 'io'.

    Returns None if PSI is unsupported by the kernel, the file does not exist,
    or the host platform is not Linux. Does not raise unhandled exceptions.
    """
    if resource not in ("cpu", "memory", "io"):
        return None

    path = os.path.join(pressure_dir, resource)
    try:
        if not os.path.isfile(path):
            return None

        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        parsed: dict[str, PsiMetrics | None] = {"some": None, "full": None}
        for line in lines:
            res = _parse_psi_line(line)
            if res:
                line_type, data = res
                parsed[line_type] = data

        # 'some' is required for valid PSI data on Linux
        if parsed["some"] is None:
            return None

        return PsiRecord(some=parsed["some"], full=parsed["full"])
    except (OSError, PermissionError, UnicodeDecodeError):
        # Gracefully handle missing privileges or OS interfaces
        return None


def compute_stall_rate(
    total_prev_us: int, total_curr_us: int, elapsed_seconds: float
) -> float:
    """Compute stall percentage rate over an elapsed time window.

    total_* are cumulative stall durations in microseconds (us).
    Returns stall rate as a percentage [0.0, 100.0].
    """
    if elapsed_seconds <= 0:
        return 0.0

    delta_us = max(0, total_curr_us - total_prev_us)
    elapsed_us = elapsed_seconds * 1_000_000.0
    stall_rate = (delta_us / elapsed_us) * 100.0
    return min(100.0, max(0.0, round(stall_rate, 2)))
