"""GameMode Lab FastAPI backend server.

Provides real-time system metrics via WebSocket, reversible performance
optimizations with write-ahead recovery, and system benchmark suites.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.benchmark import compare_benchmarks, execute_benchmark_suite
from backend.collector import Collector
from backend.db import (
    get_benchmark_by_id,
    get_benchmarks,
    init_db,
    insert_benchmark,
    update_benchmark_results,
)
from backend.models import (
    ActionResult,
    BenchmarkCompareResponse,
    BenchmarkCreate,
    BenchmarkRunItem,
    Capabilities,
    ModeRequest,
    ModeResponse,
    ProcessItem,
    StatusResponse,
)
from backend.optimizer.manager import OptimizationManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gamemode.main")

# Global instances
optimizer_manager = OptimizationManager()
collector = Collector(mode_provider=lambda: optimizer_manager.is_mode_enabled)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager: initialize DB, startup recovery, start collector, and clean shutdown."""
    logger.info("Initializing GameMode Lab backend...")
    await asyncio.to_thread(init_db)

    # Revert any dangling optimizations from previous crashed sessions
    recovered = await optimizer_manager.recover_on_startup()
    if recovered > 0:
        logger.info(f"Startup recovery completed: reverted {recovered} action(s).")

    optimizer_manager.setup_signal_handlers()
    await collector.start()

    yield

    logger.info("Shutting down GameMode Lab backend...")
    await collector.stop()
    # Always restore original OS configuration on shutdown
    await optimizer_manager.disable_mode()
    logger.info("Shutdown complete: all optimizations reverted.")


app = FastAPI(
    title="GameMode Lab",
    description="Linux gaming performance optimizer and telemetry dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Return GameMode state, system capabilities, and probe status for all actions."""
    caps = optimizer_manager.get_capabilities()
    actions = optimizer_manager.get_action_statuses()
    return StatusResponse(
        mode_enabled=optimizer_manager.is_mode_enabled,
        capabilities=Capabilities(**caps),
        actions=actions,
    )


@app.post("/api/mode", response_model=ModeResponse)
async def set_mode(payload: ModeRequest) -> ModeResponse:
    """Enable or disable GameMode performance optimizations."""
    if payload.enabled:
        results = await optimizer_manager.enable_mode()
    else:
        results = await optimizer_manager.disable_mode()

    action_results = [
        ActionResult(
            action=r["action"],
            status=r["status"],
            message=r["message"],
            undo_data=r.get("undo_data"),
        )
        for r in results
    ]
    return ModeResponse(
        mode_enabled=optimizer_manager.is_mode_enabled,
        results=action_results,
    )


@app.get("/api/processes", response_model=list[ProcessItem])
async def get_processes() -> list[ProcessItem]:
    """Return top 15 processes sorted by CPU usage."""
    procs = collector.get_top_processes()
    return [ProcessItem(**p) for p in procs]


@app.get("/api/history")
async def get_history() -> list[dict[str, Any]]:
    """Return ring buffer of recent telemetry samples (up to 300)."""
    return collector.get_history()


@app.post("/api/benchmarks")
async def create_benchmark(payload: BenchmarkCreate) -> dict[str, Any]:
    """Start an asynchronous benchmark run."""
    mode_active = optimizer_manager.is_mode_enabled
    params = {
        "repetitions": payload.repetitions,
        "synthetic_contention": payload.synthetic_contention,
    }

    bench_id = await asyncio.to_thread(
        insert_benchmark, payload.label, mode_active, params
    )

    async def _run_in_background(b_id: int, p_dict: dict[str, Any]):
        try:
            results = await asyncio.to_thread(
                execute_benchmark_suite,
                label=payload.label,
                repetitions=p_dict["repetitions"],
                synthetic_contention=p_dict["synthetic_contention"],
            )
            await asyncio.to_thread(update_benchmark_results, b_id, results)
        except Exception as e:
            logger.error(f"Benchmark run {b_id} failed: {e}", exc_info=True)
            await asyncio.to_thread(
                update_benchmark_results, b_id, {"error": str(e)}
            )

    asyncio.create_task(_run_in_background(bench_id, params))
    return {
        "id": bench_id,
        "message": f"Benchmark #{bench_id} started in background.",
    }


@app.get("/api/benchmarks", response_model=list[BenchmarkRunItem])
async def list_benchmarks(limit: int = 50) -> list[BenchmarkRunItem]:
    """List previous benchmark runs."""
    runs = await asyncio.to_thread(get_benchmarks, limit)
    return [BenchmarkRunItem(**r) for r in runs]


@app.get("/api/benchmarks/{bench_id}", response_model=BenchmarkRunItem)
async def get_benchmark(bench_id: int) -> BenchmarkRunItem:
    """Get details and results of a specific benchmark run."""
    run = await asyncio.to_thread(get_benchmark_by_id, bench_id)
    if not run:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    return BenchmarkRunItem(**run)


@app.get("/api/benchmarks/compare", response_model=BenchmarkCompareResponse)
async def compare_runs(
    a: int = Query(..., description="First benchmark run ID"),
    b: int = Query(..., description="Second benchmark run ID"),
) -> BenchmarkCompareResponse:
    """Compare two benchmark runs and compute statistical percentage changes."""
    run_a = await asyncio.to_thread(get_benchmark_by_id, a)
    run_b = await asyncio.to_thread(get_benchmark_by_id, b)

    if not run_a or not run_b:
        raise HTTPException(status_code=404, detail="One or both benchmark runs not found")

    comparison = compare_benchmarks(run_a, run_b)
    return BenchmarkCompareResponse(
        run_a=BenchmarkRunItem(**run_a),
        run_b=BenchmarkRunItem(**run_b),
        comparison=comparison,
    )


@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket):
    """Stream real-time telemetry metrics to connected web clients (1 Hz)."""
    await websocket.accept()
    subscriber_queue = collector.subscribe()

    # Send latest sample immediately on connection if available
    latest = collector.get_latest_sample()
    if latest:
        try:
            await websocket.send_json(latest)
        except Exception:
            pass

    try:
        while True:
            sample = await subscriber_queue.get()
            await websocket.send_json(sample)
    except (WebSocketDisconnect, ConnectionResetError):
        pass
    except Exception as e:
        logger.debug(f"WebSocket client disconnected: {e}")
    finally:
        collector.unsubscribe(subscriber_queue)


# Serve built React frontend if present
dist_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(dist_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_dir, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        target_file = os.path.join(dist_dir, full_path)
        if full_path and os.path.isfile(target_file):
            return FileResponse(target_file)
        return FileResponse(os.path.join(dist_dir, "index.html"))
