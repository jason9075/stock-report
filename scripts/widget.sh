#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"
if [ -n "${STOCK_REPORT_PYTHON:-}" ]; then
    exec "$STOCK_REPORT_PYTHON" -m stock_report widget --compact "$@"
fi
if [ ! -x .venv/bin/python ]; then
    uv sync --extra gui
fi
exec .venv/bin/python -m stock_report widget --compact "$@"
