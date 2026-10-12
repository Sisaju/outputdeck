#!/usr/bin/env bash
set -euo pipefail
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="${OUTPUTDECK_BIN_DIR:-${SOUNDBLASTER_BIN_DIR:-$HOME/.local/bin}}"
rm -f "$BIN_DIR/outputdeck"
rm -f "$BIN_DIR/soundblaster-control"
rm -f "$DATA_DIR/kglobalaccel/net.local.soundblaster-control.toggle.desktop"
rm -f "$DATA_DIR/applications/net.local.outputdeck.desktop"
rm -f "$DATA_DIR/applications/net.local.soundblaster-control.desktop"
rm -f "$DATA_DIR/icons/hicolor/scalable/apps/net.local.outputdeck.svg"
rm -f "$DATA_DIR/icons/hicolor/scalable/apps/net.local.soundblaster-control.svg"
rm -rf -- "$DATA_DIR/soundblaster-control"
if command -v update-desktop-database >/dev/null; then
    update-desktop-database "$DATA_DIR/applications" >/dev/null 2>&1 || true
fi
if command -v kbuildsycoca6 >/dev/null; then
    kbuildsycoca6 >/dev/null 2>&1 || true
fi
echo 'Installed app, launcher, shortcut file and icon removed. Your settings are preserved.'
