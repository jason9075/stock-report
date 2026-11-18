# Show available commands.
default:
    @just --list

# Install the application and desktop dependencies.
setup:
    if [ -z "${STOCK_REPORT_PYTHON:-}" ]; then uv sync --extra gui; fi

# Launch in the background with a system tray icon; logs: data/widget.log.
tray: setup
    @mkdir -p data
    @nohup ./scripts/widget.sh --tray > data/widget.log 2>&1 < /dev/null &
    @echo 'Widget launched in the system tray. Click the tray icon to open; choose 結束 from its menu to quit. Logs: data/widget.log'

# Open the compact widget in the foreground.
widget: setup
    ./scripts/widget.sh

# Install the Linux application menu shortcut.
desktop-install: setup
    "${STOCK_REPORT_PYTHON:-.venv/bin/python}" -m stock_report desktop-install
