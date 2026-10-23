"""System performance benchmarking suite.

Tests OS scheduling latency, multi-core CPU computation throughput, and disk I/O.
Runs strictly inside background worker threads to protect event loop responsiveness.

Global Rules:
- Benchmarks measure SYSTEM-LEVEL METRICS only (latency, throughput, PSI stalls).
- NEVER claim or mention FPS.
- If difference between runs is within measurement spread, state 'no significant change'.
"""

from __future__ import annotations

import concurrent.futures
import math
import os
import tempfile
import time
from typing import Any

from backend.psi import compute_stall_rate, parse_psi


def _measure_scheduling_latency(duration_seconds: float = 2.0) -> dict[str, float]:
    """Measure OS timer and context-switch latency.

    Repeatedly sleeps for 1 millisecond and measures the timer overshoot in microseconds.
    High scheduling latency indicates the scheduler is delayed servicing wakeups.
    """
    target_sleep = 0.001  # 1 ms
    overshoots_us: list[float] = []
    end_time = time.time() + duration_seconds

    while time.time() < end_time:
        t0 = time.perf_counter()
        time.sleep(target_sleep)
        t1 = time.perf_counter()
        actual_sleep = t1 - t0
        overshoot_us = max(0.0, (actual_sleep - target_sleep) * 1_000_000.0)
        overshoots_us.append(overshoot_us)

    if not overshoots_us:
        return {"p50_us": 0.0, "p95_us": 0.0, "p99_us": 0.0, "max_us": 0.0}

    overshoots_us.sort()
    n = len(overshoots_us)
    p50 = overshoots_us[int(n * 0.50)]
    p95 = overshoots_us[min(n - 1, int(n * 0.95))]
    p99 = overshoots_us[min(n - 1, int(n * 0.99))]
    max_val = overshoots_us[-1]

    return {
        "p50_us": round(p50, 1),
        "p95_us": round(p95, 1),
        "p99_us": round(p99, 1),
        "max_us": round(max_val, 1),
    }


def _cpu_worker(iterations: int) -> float:
    """Fixed arithmetic work computing primes / square roots."""
    val = 0.0
    for i in range(1, iterations):
        val += math.sqrt(i * 1.0001)
    return val


def _measure_cpu_workload() -> dict[str, float]:
    """Execute fixed arithmetic workload across all available CPU cores."""
    cores = os.cpu_count() or 4
    iterations_per_worker = 1_200_000
    t0 = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=cores) as executor:
        futures = [executor.submit(_cpu_worker, iterations_per_worker) for _ in range(cores)]
        concurrent.futures.wait(futures)

    elapsed = time.perf_counter() - t0
    return {"elapsed_s": round(elapsed, 4)}


def _measure_disk_io(file_size_mb: int = 64) -> dict[str, float]:
    """Measure sequential write and read throughput with explicit fsync flush."""
    data = os.urandom(1024 * 1024)  # 1 MB chunk
    total_bytes = file_size_mb * 1024 * 1024

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_name = tmp.name

    try:
        # Write test with fsync
        t0 = time.perf_counter()
        with open(tmp_name, "wb") as f:
            for _ in range(file_size_mb):
                f.write(data)
            f.flush()
            os.fsync(f.fileno())
        write_elapsed = max(0.001, time.perf_counter() - t0)
        write_mb_s = round(file_size_mb / write_elapsed, 2)

        # Read test (page cache will accelerate reads unless dropped)
        t1 = time.perf_counter()
        with open(tmp_name, "rb") as f:
            while f.read(1024 * 1024):
                pass
        read_elapsed = max(0.001, time.perf_counter() - t1)
        read_mb_s = round(file_size_mb / read_elapsed, 2)

        return {
            "write_mb_s": write_mb_s,
            "read_mb_s": read_mb_s,
        }
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except Exception:
                pass


def _calculate_stats(values: list[float]) -> dict[str, float]:
    """Compute median, min, max, and spread for a metric list."""
    if not values:
        return {"median": 0.0, "min": 0.0, "max": 0.0, "spread": 0.0}
    sorted_v = sorted(values)
    n = len(sorted_v)
    median = (sorted_v[n // 2] if n % 2 != 0 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2.0)
    min_v = sorted_v[0]
    max_v = sorted_v[-1]
    spread = max_v - min_v
    return {
        "median": round(median, 3),
        "min": round(min_v, 3),
        "max": round(max_v, 3),
        "spread": round(spread, 3),
    }


def execute_benchmark_suite(
    label: str,
    repetitions: int = 5,
    synthetic_contention: bool = False,
) -> dict[str, Any]:
    """Run full benchmark suite with warmup, multiple repetitions, and stats."""
    stop_contention = False
    contention_executor = None

    if synthetic_contention:
        # Spin 2 background CPU stress workers to introduce scheduling competition
        contention_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

        def contention_loop():
            while not stop_contention:
                math.sqrt(999999.0)

        contention_executor.submit(contention_loop)
        contention_executor.submit(contention_loop)

    try:
        # Warmup pass (discarded)
        _measure_scheduling_latency(duration_seconds=0.5)
        _measure_cpu_workload()

        # Capture PSI totals before benchmark
        psi_cpu_before = parse_psi("cpu")
        psi_mem_before = parse_psi("memory")
        psi_io_before = parse_psi("io")
        start_time = time.time()

        runs_latency_p50: list[float] = []
        runs_latency_p95: list[float] = []
        runs_latency_p99: list[float] = []
        runs_latency_max: list[float] = []
        runs_cpu_time: list[float] = []
        runs_disk_write: list[float] = []
        runs_disk_read: list[float] = []

        for _ in range(repetitions):
            lat = _measure_scheduling_latency(duration_seconds=1.5)
            cpu = _measure_cpu_workload()
            disk = _measure_disk_io(file_size_mb=32)

            runs_latency_p50.append(lat["p50_us"])
            runs_latency_p95.append(lat["p95_us"])
            runs_latency_p99.append(lat["p99_us"])
            runs_latency_max.append(lat["max_us"])
            runs_cpu_time.append(cpu["elapsed_s"])
            runs_disk_write.append(disk["write_mb_s"])
            runs_disk_read.append(disk["read_mb_s"])

        elapsed_total = max(0.001, time.time() - start_time)

        # Capture PSI totals after benchmark
        psi_cpu_after = parse_psi("cpu")
        psi_mem_after = parse_psi("memory")
        psi_io_after = parse_psi("io")

        psi_rates: dict[str, float | None] = {"cpu": None, "memory": None, "io": None}
        if psi_cpu_before and psi_cpu_after:
            psi_rates["cpu"] = compute_stall_rate(
                psi_cpu_before["some"]["total"], psi_cpu_after["some"]["total"], elapsed_total
            )
        if psi_mem_before and psi_mem_after:
            psi_rates["memory"] = compute_stall_rate(
                psi_mem_before["some"]["total"], psi_mem_after["some"]["total"], elapsed_total
            )
        if psi_io_before and psi_io_after:
            psi_rates["io"] = compute_stall_rate(
                psi_io_before["some"]["total"], psi_io_after["some"]["total"], elapsed_total
            )

        return {
            "repetitions": repetitions,
            "elapsed_seconds": round(elapsed_total, 2),
            "psi_stall_rate": psi_rates,
            "metrics": {
                "scheduling_latency_p50_us": _calculate_stats(runs_latency_p50),
                "scheduling_latency_p95_us": _calculate_stats(runs_latency_p95),
                "scheduling_latency_p99_us": _calculate_stats(runs_latency_p99),
                "scheduling_latency_max_us": _calculate_stats(runs_latency_max),
                "cpu_computation_elapsed_s": _calculate_stats(runs_cpu_time),
                "disk_write_mb_s": _calculate_stats(runs_disk_write),
                "disk_read_mb_s": _calculate_stats(runs_disk_read),
            },
            "raw_runs": {
                "latency_p95_us": runs_latency_p95,
                "cpu_elapsed_s": runs_cpu_time,
                "disk_write_mb_s": runs_disk_write,
            },
        }
    finally:
        stop_contention = True
        if contention_executor:
            contention_executor.shutdown(wait=False)


def compare_benchmarks(run_a: dict[str, Any], run_b: dict[str, Any]) -> dict[str, Any]:
    """Compare two benchmark runs using medians and noise thresholding.

    Rule: If the difference between medians is smaller than the spread (max - min)
    of either run, mark 'no significant change' to prevent false conclusions.
    """
    res_a = run_a.get("results") or {}
    res_b = run_b.get("results") or {}
    metrics_a = res_a.get("metrics") or {}
    metrics_b = res_b.get("metrics") or {}

    comparison: dict[str, Any] = {}

    for metric_name in metrics_a.keys():
        if metric_name not in metrics_b:
            continue

        stat_a = metrics_a[metric_name]
        stat_b = metrics_b[metric_name]

        med_a = stat_a.get("median", 0.0)
        med_b = stat_b.get("median", 0.0)
        spread_a = stat_a.get("spread", 0.0)
        spread_b = stat_b.get("spread", 0.0)

        delta = med_b - med_a
        max_noise = max(spread_a, spread_b)

        if med_a > 0:
            pct_change = round((delta / med_a) * 100.0, 2)
        else:
            pct_change = 0.0

        # Check significance: is change greater than measurement noise?
        significant = abs(delta) > max_noise and abs(pct_change) >= 2.0
        status_text = f"{pct_change:+.1f}%" if significant else "no significant change"

        comparison[metric_name] = {
            "median_a": med_a,
            "median_b": med_b,
            "spread_a": spread_a,
            "spread_b": spread_b,
            "percent_change": pct_change,
            "significant": significant,
            "summary": status_text,
        }

    return {
        "disclaimer": "System-level metrics only; this does not measure FPS.",
        "metrics_comparison": comparison,
    }
