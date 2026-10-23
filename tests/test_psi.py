import os
import tempfile
import pytest
from backend.psi import parse_psi, _parse_psi_line


def test_parse_psi_line_valid():
    line = "some avg10=1.23 avg60=0.45 avg300=0.10 total=987654"
    result = _parse_psi_line(line)
    assert result is not None
    line_type, metrics = result
    assert line_type == "some"
    assert metrics["avg10"] == 1.23
    assert metrics["avg60"] == 0.45
    assert metrics["avg300"] == 0.10
    assert metrics["total"] == 987654


def test_parse_psi_line_invalid():
    assert _parse_psi_line("invalid line here") is None
    assert _parse_psi_line("some avg10=abc") is None
    assert _parse_psi_line("") is None


def test_parse_psi_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        cpu_path = os.path.join(tmpdir, "cpu")
        with open(cpu_path, "w", encoding="utf-8") as f:
            f.write("some avg10=0.00 avg60=0.05 avg300=0.02 total=123456\n")

        parsed = parse_psi("cpu", pressure_dir=tmpdir)
        assert parsed is not None
        assert parsed["some"]["total"] == 123456
        assert parsed["full"] is None


def test_parse_psi_memory_with_full():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem_path = os.path.join(tmpdir, "memory")
        with open(mem_path, "w", encoding="utf-8") as f:
            f.write("some avg10=0.10 avg60=0.20 avg300=0.30 total=1000\n")
            f.write("full avg10=0.01 avg60=0.02 avg300=0.03 total=100\n")

        parsed = parse_psi("memory", pressure_dir=tmpdir)
        assert parsed is not None
        assert parsed["some"]["avg10"] == 0.10
        assert parsed["full"] is not None
        assert parsed["full"]["total"] == 100


def test_parse_psi_unsupported_resource():
    assert parse_psi("gpu") is None
    assert parse_psi("nonexistent") is None


def test_parse_psi_missing_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        assert parse_psi("cpu", pressure_dir=tmpdir) is None
