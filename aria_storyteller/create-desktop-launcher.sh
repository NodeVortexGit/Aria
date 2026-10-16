#!/usr/bin/env bash
set -euo pipefail
HERE="$(dirname "$(realpath "$0")")"
DESKTOP_DIR="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/Aria.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Aria Storyteller
Comment=Open your local Aria storyteller
Exec="$HERE/aria-launcher.sh"
Icon=web-browser
Terminal=false
Categories=Utility;AudioVideo;
StartupNotify=true
EOF
chmod +x "$DESKTOP_DIR/Aria.desktop"
echo "Created $DESKTOP_DIR/Aria.desktop"
