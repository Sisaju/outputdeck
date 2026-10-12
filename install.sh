#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$DATA_DIR/soundblaster-control"
BIN_DIR="${OUTPUTDECK_BIN_DIR:-${SOUNDBLASTER_BIN_DIR:-$HOME/.local/bin}}"
mkdir -p "$INSTALL_DIR" "$BIN_DIR"
INSTALL_DIR="$(cd -- "$INSTALL_DIR" && pwd)"
BIN_DIR="$(cd -- "$BIN_DIR" && pwd)"

# Copy only application files, never the checkout's Git data or virtualenv.
if [[ "$APP_DIR" != "$INSTALL_DIR" ]]; then
    mkdir -p "$INSTALL_DIR/soundblaster" "$INSTALL_DIR/assets"
    install -m 644 "$APP_DIR"/soundblaster/*.py "$INSTALL_DIR/soundblaster/"
    install -m 644 "$APP_DIR/assets/soundblaster.svg" "$INSTALL_DIR/assets/"
    install -m 644 "$APP_DIR/requirements.txt" "$APP_DIR/LICENSE" "$APP_DIR/README.md" "$INSTALL_DIR/"
    install -m 755 "$APP_DIR/run.sh" "$APP_DIR/install.sh" "$APP_DIR/uninstall.sh" "$INSTALL_DIR/"
fi
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt"

# Bash quoting also handles spaces and shell metacharacters in the install path.
printf '#!/usr/bin/env bash\nexec %q "$@"\n' "$INSTALL_DIR/run.sh" > "$BIN_DIR/outputdeck"
chmod +x "$BIN_DIR/outputdeck"
rm -f "$BIN_DIR/soundblaster-control"

DESKTOP_DIR="$DATA_DIR/applications"
ICON_DIR="$DATA_DIR/icons/hicolor/scalable/apps"
mkdir -p "$DESKTOP_DIR" "$ICON_DIR"
install -m 644 "$INSTALL_DIR/assets/soundblaster.svg" \
    "$ICON_DIR/net.local.outputdeck.svg"
DESKTOP_EXEC="${INSTALL_DIR//\\/\\\\}"
DESKTOP_EXEC="${DESKTOP_EXEC//\"/\\\"}"
DESKTOP_EXEC="${DESKTOP_EXEC//\`/\\\`}"
DESKTOP_EXEC="${DESKTOP_EXEC//\$/\\\$}"
DESKTOP_EXEC="${DESKTOP_EXEC//%/%%}"
cat > "$DESKTOP_DIR/net.local.outputdeck.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OutputDeck
Comment=Unofficial audio controls for Creative Sound Blaster Z
Exec="$DESKTOP_EXEC/run.sh"
Icon=net.local.outputdeck
Terminal=false
Categories=AudioVideo;Audio;
StartupNotify=true
EOF
rm -f "$DESKTOP_DIR/net.local.soundblaster-control.desktop"
rm -f "$ICON_DIR/net.local.soundblaster-control.svg"
if command -v update-desktop-database >/dev/null; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi
if command -v kbuildsycoca6 >/dev/null; then
    kbuildsycoca6 >/dev/null 2>&1 || true
fi
# KDE may remove the old action while refreshing launchers. Restore its binding
# after the refresh, then point it at the installed copy.
(cd "$INSTALL_DIR" && .venv/bin/python -c \
    'import sys; from pathlib import Path; from soundblaster.shortcuts import migrate_managed_shortcut; result = migrate_managed_shortcut(Path.cwd() / "run.sh"); print("Warning: the existing KDE shortcut could not be restored.", file=sys.stderr) if result is False else None')
echo "Installed. Open OutputDeck from your app menu or run $BIN_DIR/outputdeck."
echo "You can now move or delete the downloaded project folder."
