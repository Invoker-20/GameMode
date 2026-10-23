import os
import tempfile
import pytest
from starlette.testclient import TestClient

from backend.main import app
from backend.db import init_db


@pytest.fixture(autouse=True)
def setup_api_env(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("GAMEMODE_DB_PATH", path)
    monkeypatch.setenv("GAMEMODE_DRY_RUN", "1")
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_api_status():
    with TestClient(app) as client:
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "mode_enabled" in data
        assert "capabilities" in data
        assert "actions" in data
        assert data["capabilities"]["dry_run"] is True


def test_api_mode_toggle():
    with TestClient(app) as client:
        # Enable mode
        res_enable = client.post("/api/mode", json={"enabled": True})
        assert res_enable.status_code == 200
        data_enable = res_enable.json()
        assert data_enable["mode_enabled"] is True
        assert len(data_enable["results"]) == 3

        # Check status reflects enabled
        status_res = client.get("/api/status")
        assert status_res.json()["mode_enabled"] is True

        # Disable mode
        res_disable = client.post("/api/mode", json={"enabled": False})
        assert res_disable.status_code == 200
        data_disable = res_disable.json()
        assert data_disable["mode_enabled"] is False

        # Check status reflects disabled
        status_res2 = client.get("/api/status")
        assert status_res2.json()["mode_enabled"] is False


def test_api_processes():
    with TestClient(app) as client:
        response = client.get("/api/processes")
        assert response.status_code == 200
        procs = response.json()
        assert isinstance(procs, list)


def test_api_history():
    with TestClient(app) as client:
        response = client.get("/api/history")
        assert response.status_code == 200
        hist = response.json()
        assert isinstance(hist, list)


def test_api_benchmarks_flow():
    with TestClient(app) as client:
        # Create benchmark
        create_res = client.post(
            "/api/benchmarks",
            json={"label": "API Test Bench", "repetitions": 1, "synthetic_contention": False},
        )
        assert create_res.status_code == 200
        bench_id = create_res.json()["id"]
        assert bench_id > 0

        # List benchmarks
        list_res = client.get("/api/benchmarks")
        assert list_res.status_code == 200
        benchmarks = list_res.json()
        assert any(b["id"] == bench_id for b in benchmarks)

        # Get benchmark by id
        get_res = client.get(f"/api/benchmarks/{bench_id}")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == bench_id


def test_api_benchmarks_404():
    with TestClient(app) as client:
        res = client.get("/api/benchmarks/999999")
        assert res.status_code == 404

        comp_res = client.get("/api/benchmarks/compare?a=999998&b=999999")
        assert comp_res.status_code == 404


def test_api_websocket():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/metrics") as websocket:
            data = websocket.receive_json()
            assert "timestamp" in data
            assert "cpu" in data
            assert "memory" in data


def test_static_frontend_serving():
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        assert "<!DOCTYPE html>" in res.text or "<!doctype html>" in res.text
