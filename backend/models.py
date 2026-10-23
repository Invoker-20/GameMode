"""Pydantic v2 data models for GameMode Lab API schemas."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class Capabilities(BaseModel):
    psi: bool = Field(..., description="Whether Linux PSI (/proc/pressure) is supported")
    cpufreq: bool = Field(..., description="Whether CPU frequency scaling sysfs exists")
    governor_writable: bool = Field(..., description="Whether cpufreq governor can be modified")
    can_renice: bool = Field(..., description="Whether process niceness can be adjusted")
    swappiness_writable: bool = Field(..., description="Whether /proc/sys/vm/swappiness can be modified")
    is_root: bool = Field(..., description="Whether current process runs with root privileges (EUID==0)")
    dry_run: bool = Field(..., description="Whether dry-run mode is enabled via GAMEMODE_DRY_RUN")


class ActionStatus(BaseModel):
    name: str
    description: str
    supported: bool
    reason: str
    state: str  # idle, applied, reverted, unsupported, permission_denied, pending, error


class StatusResponse(BaseModel):
    mode_enabled: bool
    capabilities: Capabilities
    actions: list[ActionStatus]


class ModeRequest(BaseModel):
    enabled: bool


class ActionResult(BaseModel):
    action: str
    status: str  # applied, unsupported, permission_denied, error, reverted
    message: str
    undo_data: dict[str, Any] | None = None


class ModeResponse(BaseModel):
    mode_enabled: bool
    results: list[ActionResult]


class ProcessItem(BaseModel):
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    nice: int
    create_time: float


class BenchmarkCreate(BaseModel):
    label: str = Field(default="Standard Benchmark", max_length=100)
    repetitions: int = Field(default=5, ge=1, le=10)
    synthetic_contention: bool = Field(
        default=False,
        description="Whether to spin synthetic background load workers during benchmark"
    )


class BenchmarkRunItem(BaseModel):
    id: int
    started_at: str
    label: str
    mode_enabled: bool
    params: dict[str, Any]
    results: dict[str, Any] | None = None


class BenchmarkCompareResponse(BaseModel):
    run_a: BenchmarkRunItem
    run_b: BenchmarkRunItem
    comparison: dict[str, Any]
