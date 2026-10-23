import pytest
from backend.benchmark import (
    _calculate_stats,
    compare_benchmarks,
    _measure_scheduling_latency,
    _measure_cpu_workload,
    _measure_disk_io,
    execute_benchmark_suite,
)


def test_calculate_stats_empty():
    stats = _calculate_stats([])
    assert stats["median"] == 0.0
    assert stats["spread"] == 0.0


def test_calculate_stats_values():
    stats = _calculate_stats([10.0, 20.0, 30.0])
    assert stats["median"] == 20.0
    assert stats["min"] == 10.0
    assert stats["max"] == 30.0
    assert stats["spread"] == 20.0


def test_compare_benchmarks_no_change_due_to_noise():
    run_a = {
        "results": {
            "metrics": {
                "scheduling_latency_p95_us": {
                    "median": 100.0,
                    "spread": 15.0,
                    "min": 90.0,
                    "max": 105.0,
                }
            }
        }
    }
    # med_b delta is only 5.0, but spread is 15.0, so no significant change
    run_b = {
        "results": {
            "metrics": {
                "scheduling_latency_p95_us": {
                    "median": 95.0,
                    "spread": 12.0,
                    "min": 90.0,
                    "max": 102.0,
                }
            }
        }
    }
    res = compare_benchmarks(run_a, run_b)
    assert not res["metrics_comparison"]["scheduling_latency_p95_us"]["significant"]
    assert res["metrics_comparison"]["scheduling_latency_p95_us"]["summary"] == "no significant change"


def test_compare_benchmarks_significant_change():
    run_a = {
        "results": {
            "metrics": {
                "scheduling_latency_p95_us": {
                    "median": 200.0,
                    "spread": 10.0,
                    "min": 195.0,
                    "max": 205.0,
                }
            }
        }
    }
    run_b = {
        "results": {
            "metrics": {
                "scheduling_latency_p95_us": {
                    "median": 150.0,
                    "spread": 10.0,
                    "min": 145.0,
                    "max": 155.0,
                }
            }
        }
    }
    res = compare_benchmarks(run_a, run_b)
    comp = res["metrics_comparison"]["scheduling_latency_p95_us"]
    assert comp["significant"] is True
    assert comp["percent_change"] == -25.0
    assert "-25.0%" in comp["summary"]


def test_measure_micro_benchmarks():
    lat = _measure_scheduling_latency(duration_seconds=0.1)
    assert "p50_us" in lat
    assert "p95_us" in lat
    assert lat["p95_us"] >= 0.0

    cpu = _measure_cpu_workload()
    assert cpu["elapsed_s"] > 0.0

    disk = _measure_disk_io(file_size_mb=4)
    assert disk["write_mb_s"] > 0.0
    assert disk["read_mb_s"] > 0.0
