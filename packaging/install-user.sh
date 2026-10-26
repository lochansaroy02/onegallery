#!/usr/bin/env bash
# Install a launcher for a source checkout into ~/.local (no root needed).
# Run from anywhere:  ./packaging/install-user.sh      Undo:  ./packaging/install-user.sh --uninstall
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data="${XDG_DATA_HOME:-$HOME/.local/share}"
bin="$HOME/.local/bin"

# the app used to be called LGallery: its launcher, menu entry and icon are replaced
old_files=("$bin/lgallery" "$data/applications/lgallery.desktop" "$data/icons/hicolor/scalable/apps/lgallery.svg")

if [[ "${1:-}" == "--uninstall" ]]; then
    rm -f "$bin/onegallery" "$data/applications/onegallery.desktop" \
          "$data/icons/hicolor/scalable/apps/onegallery.svg" "${old_files[@]}"
    update-desktop-database "$data/applications" 2>/dev/null || true
    echo "Launcher removed (your index and settings were left in place)."
    exit 0
fi

python="$here/.venv/bin/python"
if [[ ! -x "$python" ]]; then
    python="$(command -v python3)"
    echo "No .venv found, using system $python"
fi

mkdir -p "$bin" "$data/applications" "$data/icons/hicolor/scalable/apps"
rm -f "${old_files[@]}"
cat > "$bin/onegallery" <<SH
#!/bin/sh
exec "$python" "$here/main.py" "\$@"
SH
chmod +x "$bin/onegallery"
install -m644 "$here/packaging/icon.svg" "$data/icons/hicolor/scalable/apps/onegallery.svg"
sed -e "s|^Exec=.*|Exec=$bin/onegallery %F|" -e "s|^TryExec=.*|TryExec=$bin/onegallery|" \
    "$here/packaging/onegallery.desktop" > "$data/applications/onegallery.desktop"
update-desktop-database "$data/applications" 2>/dev/null || true
kbuildsycoca6 2>/dev/null || kbuildsycoca5 2>/dev/null || true
echo "Installed. 'One Gallery' is now in the application launcher (command: $bin/onegallery)."
echo "To open pictures from Dolphin in One Gallery: One Gallery > Settings > Set as default,"
echo "or in Dolphin right-click a picture > Open With > One Gallery."
