#!/usr/bin/env bash
# KYA — Local development launcher for macOS
# Usage: ./run.sh [--test | --serve | --both]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KYA_DIR="$SCRIPT_DIR/kya"
VENV_DIR="$SCRIPT_DIR/.venv"
PORT="${KYA_PORT:-8000}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[KYA]${NC} $1"; }
ok()    { echo -e "${GREEN}[KYA]${NC} $1"; }
warn()  { echo -e "${YELLOW}[KYA]${NC} $1"; }

# ─── Check Python ──────────────────────────────────────────────────────
check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON=python3
    elif command -v python &>/dev/null; then
        PYTHON=python
    else
        echo "Error: Python 3.11+ is required. Install from https://www.python.org/downloads/"
        exit 1
    fi

    version=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 11 ]; }; then
        echo "Error: Python 3.11+ required (found $version)"
        exit 1
    fi
    ok "Python $version"
}

# ─── Virtual environment ───────────────────────────────────────────────
setup_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        info "Creating virtual environment..."
        $PYTHON -m venv "$VENV_DIR"
    fi
    source "$VENV_DIR/bin/activate"
    ok "Virtual environment active"
}

# ─── Install dependencies ─────────────────────────────────────────────
install_deps() {
    info "Installing dependencies..."
    pip install --quiet --upgrade pip
    pip install --quiet -e "$KYA_DIR[dev]"
    ok "Dependencies installed"
}

# ─── Run tests ─────────────────────────────────────────────────────────
run_tests() {
    info "Running tests..."
    echo ""
    cd "$KYA_DIR"
    python -m pytest tests/ -v --tb=short
    cd "$SCRIPT_DIR"
    echo ""
    ok "All tests passed"
}

# ─── Start server ─────────────────────────────────────────────────────
start_server() {
    cd "$KYA_DIR"
    echo ""
    ok "Starting KYA server on http://localhost:$PORT"
    info "Dashboard UI:  http://localhost:$PORT/ui"
    info "API docs:      http://localhost:$PORT/docs"
    info "Health check:  http://localhost:$PORT/health"
    echo ""
    info "Press Ctrl+C to stop"
    echo ""
    python -m uvicorn kya.main:app --host 0.0.0.0 --port "$PORT" --reload
}

# ─── Main ──────────────────────────────────────────────────────────────
main() {
    echo ""
    echo "  ╔═══════════════════════════════════╗"
    echo "  ║   KYA — Know Your Agent           ║"
    echo "  ║   Local Development Environment   ║"
    echo "  ╚═══════════════════════════════════╝"
    echo ""

    check_python
    setup_venv
    install_deps

    MODE="${1:---both}"

    case "$MODE" in
        --test)
            run_tests
            ;;
        --serve)
            start_server
            ;;
        --both)
            run_tests
            start_server
            ;;
        *)
            echo "Usage: ./run.sh [--test | --serve | --both]"
            echo ""
            echo "  --test   Run tests only"
            echo "  --serve  Start the dev server only"
            echo "  --both   Run tests then start server (default)"
            exit 1
            ;;
    esac
}

main "$@"
