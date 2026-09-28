#!/usr/bin/env bash
# ===================================================================
# ECDC HA-BSI Surveillance & Benchmark AI Platform
# Portable Universal Launcher (Linux / macOS)
# ===================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==================================================================="
echo "    ECDC HA-BSI Surveillance & Benchmark AI Platform"
echo "    Algoritmo Deterministico ECDC PPS (ECDC/2025/LVP/0005)"
echo "==================================================================="
echo ""

# 1. Check Python 3
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "[CRITICAL ERROR] Python not found. Please install Python 3.10+."
    exit 1
fi

# 2. Check Ollama daemon
echo "[*] Verifying Ollama service status..."
if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "[OK] Ollama service active and ready."
else
    echo "[!] Ollama service not detected."
    if command -v ollama >/dev/null 2>&1; then
        echo "    Attempting to start Ollama daemon in background..."
        ollama serve >/dev/null 2>&1 &
        sleep 2
    else
        echo "[WARNING] Ollama not found in PATH. Please start it manually if needed."
    fi
fi

# 3. Launch Web Dashboard
echo ""
echo "[*] Launching Web Control Dashboard on: http://127.0.0.1:5050"
echo "Press Ctrl+C to stop the server."
echo "-------------------------------------------------------------------"

# Apertura automatica browser (xdg-open su Linux, open su macOS)
if command -v xdg-open >/dev/null 2>&1; then
    (sleep 2 && xdg-open http://127.0.0.1:5050) &
elif command -v open >/dev/null 2>&1; then
    (sleep 2 && open http://127.0.0.1:5050) &
fi

$PYTHON_CMD run_pipeline.py --ui
