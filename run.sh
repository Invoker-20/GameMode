#!/usr/bin/env bash
# GameMode Lab — Runner Script
# Safely launches backend and serves dashboard on 127.0.0.1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "         GameMode Lab Runner              "
echo "=========================================="

# Check Python 3
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "[-] Python is required but not installed." >&2
    exit 1
fi

PY_BIN="$(command -v python3 || command -v python)"
echo "[+] Using Python: $($PY_BIN --version)"

# Check or build frontend if dist is missing
if [ ! -d "frontend/dist" ]; then
    echo "[*] Frontend build missing. Building frontend..."
    if command -v npm &>/dev/null; then
        (cd frontend && npm install && npm run build)
    else
        echo "[!] npm not found; frontend will not be pre-built. Dashboard will serve API only."
    fi
fi

# Dry run notice if enabled
if [ "${GAMEMODE_DRY_RUN:-0}" = "1" ]; then
    echo "[!] Running in DRY-RUN mode (GAMEMODE_DRY_RUN=1). Sysfs/procfs modifications will be simulated."
fi

# Run uvicorn on 127.0.0.1:8000
echo "[+] Starting GameMode Lab server on http://127.0.0.1:8000"
echo "[+] Press Ctrl+C to stop cleanly (optimizations will be reverted automatically)"

exec "$PY_BIN" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
