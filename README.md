# GameMode Lab 🎮

**Linux Gaming Performance Optimizer & Real-Time Telemetry Dashboard**

GameMode Lab is a lightweight, safe, and fully reversible Linux system performance optimizer designed for low-latency gaming. It provides live OS telemetry via WebSockets, applies write-ahead crash-safe system optimizations, and measures system-level performance deltas without snake-oil claims.

---

## Architecture & Core Design Principles

1. **Write-Ahead Reversible Optimizations**:
   Before any system parameter is modified (`cpufreq`, `vm.swappiness`, or process nice levels), an undo record is written to a local SQLite database (`gamemode.db`) with state `pending`. Once applied, the record is marked `applied`. When disabling GameMode or shutting down, optimizations are reverted in LIFO (reverse) order and marked `reverted`.

2. **Crash-Resilient Startup Recovery**:
   If the daemon or system abruptly terminates while optimizations are active, the startup lifespan detects any `pending` or `applied` records and immediately rolls the OS back to its original configuration before servicing new requests.

3. **PID Reuse Protection**:
   Process renicing tracks `(pid, create_time)` pairs. If a background process terminates during a gaming session and the Linux kernel recycles its PID to a different process, GameMode Lab detects the timestamp mismatch and will not modify the unrelated process.

4. **Non-Blocking Async Telemetry**:
   CPU and disk metrics, PSI parsing, and benchmark suites run in dedicated background threads (`asyncio.to_thread` / `ThreadPoolExecutor`). The asyncio event loop remains responsive and never stutters WebSocket delivery.

5. **Honest, Scientifically Grounded Benchmarks**:
   **GameMode Lab strictly does NOT claim or measure FPS.** Games are complex graphics pipelines governed by GPU limits, shader compilation, and engine architecture. GameMode Lab measures purely system-level metrics (scheduler wakeup latency, multi-core arithmetic throughput, and disk I/O). If measured differences are within run-to-run noise spread, the dashboard explicitly reports **"no significant change"**.

---

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, Uvicorn, psutil, Pydantic v2, SQLite3 (via `asyncio.to_thread`)
- **Frontend**: React 18, Vite (JavaScript), Recharts, Pure Responsive CSS (no external CSS framework)
- **Linux Interfaces**: `/proc/pressure` (PSI), `/proc/sys/vm/swappiness`, `/sys/devices/system/cpu/cpu*/cpufreq`
- **Network**: Binds to `127.0.0.1` only. WebSocket streaming at 1 Hz.

---

## Directory Structure

```
gamemode-lab/
├── backend/
│   ├── main.py             # FastAPI app, lifespan, REST endpoints, WebSocket
│   ├── collector.py        # 1 Hz metric collector & 3s process scanner
│   ├── psi.py              # Linux Pressure Stall Information (/proc/pressure) parser
│   ├── models.py           # Pydantic v2 schemas
│   ├── db.py               # SQLite write-ahead undo logs & benchmark storage
│   ├── benchmark.py        # Scheduling latency, CPU, and disk I/O benchmarks
│   ├── requirements.txt    # Python dependencies
│   └── optimizer/
│       ├── base.py         # Abstract Action interface and dry-run/root checks
│       ├── governor.py     # CPU scaling governor switch (performance)
│       ├── renice.py       # Background task deprioritization (+10 nice)
│       ├── swappiness.py   # VM anonymous page swappiness tuning (10)
│       └── manager.py      # Action registry, write-ahead logging & recovery
├── frontend/
│   ├── package.json        # React 18 & Recharts dependencies
│   ├── vite.config.js      # Vite proxy configuration (/api and /ws -> :8000)
│   ├── index.html          # HTML entry point
│   └── src/
│       ├── main.jsx        # React root
│       ├── App.jsx         # Dashboard container
│       ├── api.js          # REST API client
│       ├── styles.css      # Dark theme styling
│       ├── hooks/
│       │   └── useMetrics.js # Auto-reconnecting WebSocket hook (120s buffer)
│       └── components/
│           ├── ModeToggle.jsx     # Optimizer state & capabilities
│           ├── MetricsCharts.jsx  # Recharts live telemetry (CPU, Mem, Disk, PSI)
│           ├── ProcessTable.jsx   # Top 15 processes by CPU/Memory
│           └── BenchmarkPanel.jsx # Latency benchmark runner & statistical diff
├── README.md
└── run.sh
```

---

## Setup & Quickstart

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm

### 1. Install Backend Dependencies
```bash
pip install -r backend/requirements.txt
```

### 2. Build Frontend
```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. Run the Server
```bash
# Standard run (binds to 127.0.0.1:8000 and serves dashboard)
bash run.sh
# or directly via python:
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Open **`http://127.0.0.1:8000`** in your browser. Interactive API docs are available at **`http://127.0.0.1:8000/docs`**.

---

## Sudo / Privileges & Security Model

### Why Root is Required on Linux
1. **CPU Frequency Scaling (`/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`)**:
   Writing to cpufreq sysfs nodes requires `CAP_SYS_ADMIN` or root permissions.
2. **Virtual Memory Swappiness (`/proc/sys/vm/swappiness`)**:
   Tuning system-wide memory paging thresholds requires root permissions.
3. **Restoring Process Niceness (`CAP_SYS_NICE`)**:
   Under Linux security semantics, an unprivileged user can *increase* their own processes' nice level (lower priority), but *cannot decrease* nice back to 0 without `CAP_SYS_NICE` or root.

### Running with Sudo
To allow GameMode Lab to apply hardware governor switches and swappiness modifications on Linux:
```bash
sudo $(which python) -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### Degraded Modes (Graceful Degradation)
- **Unprivileged (Non-Root)**: The backend starts normally. `probe()` reports `permission_denied` with descriptive messages for privileged actions rather than raising unhandled exceptions.
- **Dry-Run Mode (`GAMEMODE_DRY_RUN=1`)**:
  ```bash
  export GAMEMODE_DRY_RUN=1
  bash run.sh
  ```
  In dry-run mode, actions log simulated operations and record fake undo logs. This allows testing the complete UI, WebSocket streaming, and recovery flow on any workstation without root or sysfs interfaces.

### Safety Denylist
The renice optimizer will **never** modify the priority of:
- PID 1 (`init` / `systemd`)
- Kernel threads (`kthreadd`, PPID == 2)
- GameMode Lab daemon and its parent processes
- Display servers and compositors (`Xorg`, `Xwayland`, `gnome-shell`, `kwin`, `mutter`, `plasmashell`, `sway`, `hyprland`)
- Real-time audio pipelines (`pipewire`, `pulseaudio`, `jackd`)

---

## Hardware-Dependent Features

1. **CPU Frequency Scaling Drivers**:
   - Modern Intel CPUs use `intel_pstate` (active mode exposes `powersave` and `performance` governors).
   - Modern AMD CPUs use `amd-pstate` or `acpi-cpufreq`.
   - Virtual machines or systems without frequency scaling drivers report `unsupported`.

2. **Pressure Stall Information (PSI)**:
   - Introduced in Linux Kernel 4.20 (`CONFIG_PSI=y`).
   - Located at `/proc/pressure/{cpu,memory,io}`.
   - Distinguishes between **`some`** (at least one runnable task delayed) and **`full`** (all non-idle tasks stalled, CPU cycles lost).
   - If missing (e.g. WSL1, macOS, BSD, Windows, or kernels built without `CONFIG_PSI`), the dashboard displays an educational banner without crashing.

3. **Thermal Monitoring**:
   - Reads hardware thermal zones from `/sys/class/thermal` or `hwmon` via `psutil.sensors_temperatures()`.
   - Automatically falls back to `null` if temperature sensors are absent.

---

## Honest Benchmark Methodology

GameMode Lab includes a built-in synthetic benchmark suite:
- **Scheduling Latency Test**: Repeatedly sleeps for 1.0 ms and records timer overshoot in microseconds. Reports p50, p95, p99, and max. Demonstrates scheduler responsiveness under load.
- **CPU Workload**: Multi-core arithmetic calculation across all cores (`os.cpu_count()`). Measures elapsed calculation seconds.
- **Sequential Disk I/O**: Writes and reads temporary files with explicit `fsync` flushing. Reports write and read MB/s.
- **Synthetic Contention**: Optional background load threads to measure optimizer efficacy under contention.

### Statistical Differential Comparison
When comparing two benchmark runs (e.g. Baseline vs Optimized):
- Medians across repetitions are compared.
- If the percent change between medians is smaller than the larger of the two runs' measurement spread (`max - min`), the UI marks the result **"no significant change"**.
- This prevents reporting false improvements caused by standard CPU clock jitter or background system noise.

---

## Scope Limitations

The following features were intentionally excluded to maintain system safety and architectural clarity:
- **`drop_caches`**: Linux page cache improves game asset loading. Dropping caches hurts performance and causes disk thrashing.
- **GPU Overclocking / Driver Tuning**: Vendor-dependent and carries hardware damage risks.
- **`SCHED_FIFO` / Realtime scheduling**: Giving games realtime priority risks desktop deadlocks if a game freezes.
- **Game Process Auto-Detection**: Heuristic process guessing is fragile across Proton/Wine and Steam wrappers.

---

## Verification & Acceptance Tests

| Check | Requirement | Result |
|---|---|---|
| 1 | `parse_psi('cpu')` prints data on PSI Linux or `None` on unsupported platforms without crashing | **PASSED** |
| 2 | Backend starts on `127.0.0.1:8000` and `/docs` loads (HTTP 200) | **PASSED** |
| 3 | WebSocket client receives 1 Hz JSON telemetry stream | **PASSED** |
| 4 | Dry-run toggle ON then OFF leaves `undo_log` with all records marked `reverted` | **PASSED** |
| 5 | Real Linux with sudo reverts governors, swappiness, and nice values | **PASSED** |
| 6 | Unclean shutdown while GameMode is active triggers startup recovery revert | **PASSED** |
| 7 | `npm run build` succeeds and backend serves production dashboard from `frontend/dist` | **PASSED** |
| 8 | Multi-repetition benchmark suite executes, stores to SQLite, and computes statistical comparison | **PASSED** |
