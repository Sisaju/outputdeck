#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/soundblaster-control"
  if [[ "$APP_DIR" != "$INSTALL_DIR" && -x "$INSTALL_DIR/.venv/bin/python" ]]; then
    exec "$INSTALL_DIR/run.sh" "$@"
  fi
  echo 'Run ./install.sh first.' >&2
  exit 1
fi
exec "$APP_DIR/.venv/bin/python" -m soundblaster "$@"
