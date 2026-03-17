#!/usr/bin/env bash
# Cross-platform wrapper for running Python with cairosvg.
#
# macOS (Homebrew): sets DYLD_LIBRARY_PATH so cairosvg finds libcairo.
# Linux: libcairo is a system library — no extra path needed.
#
# Usage:
#   ./run.sh render_test.py
#   ./run.sh main.py
set -euo pipefail

if [[ "$(uname)" == "Darwin" ]]; then
  export DYLD_LIBRARY_PATH="/opt/homebrew/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
fi

exec venv/bin/python "$@"
