#!/bin/zsh
cd -- "${0:A:h}"
PYTHON_BIN="/Users/theoneglobal/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
if [[ ! -x "$PYTHON_BIN" ]]; then PYTHON_BIN="$(command -v python3)"; fi
exec "$PYTHON_BIN" hunt.py serve --open
