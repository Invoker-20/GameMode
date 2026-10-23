"""System metric and process collector.

Samples CPU, Memory, Disk I/O, PSI (Pressure Stall Information), and process
metrics without blocking the asyncio event loop.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import logging
import os
import sys
import time
from typing import Any, Callable, Coroutine

import psutil

from backend.psi import parse_psi

logger = logging.getLogger("gamemode.collector")


class Collector:
    """Collects real-time OS performance metrics and top processes."""

    def __init__(self, mode_provider: Callable[[], bool] | None = None) -> None:
        self.mode_provider = mode_provider
        self._samples: deque[dict[str, Any]] = deque(maxlen=300)
        self._top_processes: list[dict[str, Any]] = []
        self._process_cache: dict[int, psutil.Process] = {}
        self._last_disk_io: tuple[int, int, float] | None = None
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._running = False
        self._collection_task: asyncio.Task[None] | None = None
        self._process_task: asyncio.Task[None] | None = None

        # Prime psutil CPU percent calculation (the first call always returns 0.0)
        try:
            psutil.cpu_percent(interval=None)
            psutil.cpu_percent(interval=None, percpu=True)
        except Exception:
            pass

    @property
    def is_mode_enabled(self) -> bool:
        """Query if GameMode is active."""
        if self.mode_provider:
            return bool(self.mode_provider())
        return False

    def get_latest_sample(self) -> dict[str, Any] | None:
        """Return the most recent metric sample."""
        return self._samples[-1] if self._samples else None

    def get_history(self) -> list[dict[str, Any]]:
        """Return the ring buffer of recent samples (up to 300)."""
        return list(self._samples)

    def get_top_processes(self) -> list[dict[str, Any]]:
        """Return the cached top 15 processes by CPU usage."""
        return list(self._top_processes)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Register a queue to receive real-time metric samples."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=30)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove a subscriber queue."""
        self._subscribers.discard(q)

    def _broadcast(self, sample: dict[str, Any]) -> None:
        """Broadcast a sample to all active WebSocket subscriber queues."""
        for q in list(self._subscribers):
            try:
                q.put_nowait(sample)
            except asyncio.QueueFull:
                # Discard oldest sample if a client is slow
                try:
                    q.get_nowait()
                    q.put_nowait(sample)
                except Exception:
                    pass

    def _read_temperature(self) -> float | None:
        """Attempt to read CPU temperature via psutil /sys/class/thermal.

        On Linux, psutil reads /sys/class/thermal or coretemp/k10temp hwmon.
        Hardware without sensors, virtual machines, or non-Linux OS will return None.
        """
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    for name in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
                        if name in temps and temps[name]:
                            return round(temps[name][0].current, 1)
                    # Fallback to the first available sensor
                    for entries in temps.values():
                        if entries:
                            return round(entries[0].current, 1)
        except Exception:
            pass
        return None

    def _sample_system(self) -> dict[str, Any]:
        """Perform a single snapshot of system metrics. Synchronous OS queries."""
        now = time.time()
        iso_time = datetime.now(timezone.utc).isoformat()

        # 1. CPU metrics
        # cpu_percent(interval=None) compares delta Jiffies in /proc/stat since last call
        cpu_total = float(psutil.cpu_percent(interval=None))
        per_core = [float(v) for v in psutil.cpu_percent(interval=None, percpu=True)]

        freq_mhz: float | None = None
        try:
            freq = psutil.cpu_freq()
            if freq and freq.current > 0:
                freq_mhz = round(freq.current, 1)
        except Exception:
            freq_mhz = None

        # Linux load average represents tasks in R (running) and D (uninterruptible disk wait) states
        load_avg: list[float] = [0.0, 0.0, 0.0]
        try:
            if hasattr(os, "getloadavg"):
                load_avg = [round(x, 2) for x in os.getloadavg()]
        except Exception:
            load_avg = [0.0, 0.0, 0.0]

        # 2. Memory metrics (/proc/meminfo)
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        mem_data = {
            "percent": round(vm.percent, 1),
            "used": vm.used,
            "available": vm.available,
            "swap_percent": round(swap.percent, 1),
        }

        # 3. Disk I/O delta (/proc/diskstats)
        read_bytes_per_s = 0.0
        write_bytes_per_s = 0.0
        try:
            disk_io = psutil.disk_io_counters()
            if disk_io is not None:
                curr_read = disk_io.read_bytes
                curr_write = disk_io.write_bytes
                if self._last_disk_io is not None:
                    prev_read, prev_write, prev_time = self._last_disk_io
                    elapsed = max(0.001, now - prev_time)
                    read_bytes_per_s = max(0.0, round((curr_read - prev_read) / elapsed, 1))
                    write_bytes_per_s = max(0.0, round((curr_write - prev_write) / elapsed, 1))
                self._last_disk_io = (curr_read, curr_write, now)
        except Exception:
            pass

        # 4. PSI Pressure Stall Information (/proc/pressure/*)
        psi_data = {
            "cpu": parse_psi("cpu"),
            "memory": parse_psi("memory"),
            "io": parse_psi("io"),
        }

        # 5. Temperature
        temp_c = self._read_temperature()

        return {
            "timestamp": iso_time,
            "epoch": round(now, 3),
            "cpu": {
                "total_percent": cpu_total,
                "per_core": per_core,
                "freq_mhz": freq_mhz,
                "load_avg": load_avg,
            },
            "memory": mem_data,
            "disk": {
                "read_bytes_per_s": read_bytes_per_s,
                "write_bytes_per_s": write_bytes_per_s,
            },
            "psi": psi_data,
            "temperature_c": temp_c,
            "mode_enabled": self.is_mode_enabled,
        }

    def _sync_refresh_processes(self) -> list[dict[str, Any]]:
        """Refresh process CPU & memory in a background thread.

        psutil requires persistent Process instances across calls so that proc.cpu_percent()
        can calculate the time difference (utime + stime) between two successive calls.
        """
        seen_pids: set[int] = set()
        active_processes: list[dict[str, Any]] = []

        try:
            pids = psutil.pids()
        except Exception:
            return []

        for pid in pids:
            seen_pids.add(pid)
            proc = self._process_cache.get(pid)
            if proc is None:
                try:
                    proc = psutil.Process(pid)
                    # Initialize CPU tracker (first call returns 0.0)
                    proc.cpu_percent(None)
                    self._process_cache[pid] = proc
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            try:
                name = proc.name()
                cpu = proc.cpu_percent(None)
                mem = proc.memory_percent()
                raw_nice = proc.nice()
                nice = int(raw_nice) if raw_nice is not None else 0
                create_time = proc.create_time()

                active_processes.append(
                    {
                        "pid": pid,
                        "name": name,
                        "cpu_percent": round(cpu, 1),
                        "memory_percent": round(mem, 2),
                        "nice": nice,
                        "create_time": create_time,
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception:
                continue

        # Evict terminated PIDs from cache
        stale_pids = set(self._process_cache.keys()) - seen_pids
        for spid in stale_pids:
            self._process_cache.pop(spid, None)

        # Sort top 15 by CPU percent descending
        active_processes.sort(key=lambda p: p["cpu_percent"], reverse=True)
        return active_processes[:15]

    async def _metrics_loop(self) -> None:
        """Collect system metrics once per second."""
        while self._running:
            try:
                sample = await asyncio.to_thread(self._sample_system)
                self._samples.append(sample)
                self._broadcast(sample)
            except Exception as e:
                logger.error(f"Error in metrics loop: {e}", exc_info=True)
            await asyncio.sleep(1.0)

    async def _processes_loop(self) -> None:
        """Collect top 15 processes every 3 seconds."""
        while self._running:
            try:
                top_procs = await asyncio.to_thread(self._sync_refresh_processes)
                self._top_processes = top_procs
            except Exception as e:
                logger.error(f"Error in process collector: {e}", exc_info=True)
            await asyncio.sleep(3.0)

    async def start(self) -> None:
        """Start the background sampling tasks."""
        if self._running:
            return
        self._running = True
        self._collection_task = asyncio.create_task(self._metrics_loop())
        self._process_task = asyncio.create_task(self._processes_loop())
        logger.info("Collector background tasks started.")

    async def stop(self) -> None:
        """Stop background sampling tasks cleanly."""
        self._running = False
        for task in (self._collection_task, self._process_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("Collector stopped.")
