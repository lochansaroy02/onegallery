#!/usr/bin/env bash
# Build One Gallery for macOS: "dist/One Gallery.app" and dist/OneGallery-<version>-macos-<arch>.dmg.
#
#   packaging/macos/build.sh [--no-faces] [--no-ffmpeg] [--skip-tests] [--no-dmg]
#
# Builds for the Mac it runs on (Apple Silicon: arm64, Intel: x86_64). It:
#   1. makes build/venv-mac and installs the Python packages;
#   2. downloads ffmpeg and ffprobe (static builds from ffmpeg.martin-riedl.de) for video thumbnails;
#   3. runs the unit tests;
#   4. bundles everything with PyInstaller (packaging/macos/onegallery.spec);
#   5. signs the app ad hoc (no Apple Developer account: macOS asks people to allow it once);
#   6. checks the bundled app with --self-test: interface, video playback, printing and ffmpeg;
#   7. packs it into a .dmg with a shortcut to Applications.
#
# --no-faces leaves out OpenCV (People), --no-ffmpeg leaves out video thumbnails (Homebrew's
# ffmpeg is used when it is installed), --skip-tests skips step 3, --no-dmg stops after the app.
# Set PYTHON to choose the Python for build/venv-mac (default: python3.13, else python3), or
# BUILD_PYTHON to build with an existing environment's Python instead (saves disk space).
set -euo pipefail

faces=1 ffmpeg=1 tests=1 dmg=1
for arg in "$@"; do
    case "$arg" in
        --no-faces) faces=0 ;;
        --no-ffmpeg) ffmpeg=0 ;;
        --skip-tests) tests=0 ;;
        --no-dmg) dmg=0 ;;
        -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
step() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$1" >&2; exit 1; }

[[ "$(uname -s)" == Darwin ]] || fail "this script builds the macOS app; run it on a Mac"
version="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' backend/__init__.py)"
arch="$(uname -m)"   # arm64 or x86_64
printf '\033[1;32mOne Gallery %s for macOS (%s)\033[0m\n' "$version" "$arch"

# ---- 1. Python environment -----------------------------------------------------------------
if [[ -n "${BUILD_PYTHON:-}" ]]; then
    step "Python environment ($BUILD_PYTHON)"
    py="$BUILD_PYTHON"
else
    step "Python environment (build/venv-mac)"
    python="${PYTHON:-$(command -v python3.13 || command -v python3)}"
    if [[ ! -x build/venv-mac/bin/python ]]; then
        "$python" -m venv build/venv-mac
    fi
    py="$root/build/venv-mac/bin/python"
fi
"$py" -m pip install --quiet --upgrade pip
requirements="$(mktemp)"
if [[ $faces -eq 1 ]]; then
    cp requirements.txt "$requirements"
else
    grep -v '^opencv' requirements.txt > "$requirements"
fi
"$py" -m pip install --quiet -r "$requirements" pyinstaller
rm -f "$requirements"

# ---- 2. ffmpeg --------------------------------------------------------------------------------
ff="$root/build/ffmpeg-mac"
if [[ $ffmpeg -eq 1 ]]; then
    step "ffmpeg (static build from ffmpeg.martin-riedl.de)"
    case "$arch" in arm64) ffarch=arm64 ;; x86_64) ffarch=amd64 ;; *) fail "unknown Mac architecture $arch" ;; esac
    mkdir -p "$ff"
    for tool in ffmpeg ffprobe; do
        if [[ ! -x "$ff/$tool" ]]; then
            curl -fsSL -o "$ff/$tool.zip" "https://ffmpeg.martin-riedl.de/redirect/latest/macos/$ffarch/release/$tool.zip"
            unzip -o -q "$ff/$tool.zip" -d "$ff"
            rm -f "$ff/$tool.zip"
            chmod +x "$ff/$tool"
        fi
    done
    "$ff/ffmpeg" -hide_banner -version | head -1
    cat > "$ff/README.txt" <<'TXT'
ffmpeg and ffprobe make video thumbnails and read video details in One Gallery.

They are the FFmpeg project's tools (https://ffmpeg.org), in the static macOS builds from
https://ffmpeg.martin-riedl.de. FFmpeg is licensed under the GNU GPL / LGPL; its source code is
at https://ffmpeg.org/download.html. They run as separate programs and are not part of
One Gallery's own code, which is MIT licensed.
TXT
    export ONEGALLERY_FFMPEG_DIR="$ff"
else
    export ONEGALLERY_FFMPEG_DIR="$root/build/no-ffmpeg"
fi

# ---- 3. tests --------------------------------------------------------------------------------
if [[ $tests -eq 1 ]]; then
    step "Unit tests"
    QT_QPA_PLATFORM=offscreen PATH="$ONEGALLERY_FFMPEG_DIR:$PATH" "$py" -m unittest discover -s tests
fi

# ---- 4. PyInstaller -----------------------------------------------------------------------------
step "PyInstaller (dist/One Gallery.app)"
rm -rf "dist/One Gallery.app" dist/OneGallery
"$py" -m PyInstaller packaging/macos/onegallery.spec --noconfirm --distpath dist --workpath build/pyinstaller-mac
app="$root/dist/One Gallery.app"

# ---- 5. ad-hoc signature -------------------------------------------------------------------------
# Apple Silicon only runs signed code. Without a Developer ID, the app is signed "ad hoc":
# it runs, and Gatekeeper asks people to allow it once (System Settings > Privacy & Security).
step "Signing ad hoc"
xattr -cr "$app"
codesign --force --deep --sign - "$app"
codesign --verify --deep --strict "$app"
echo "    signature ok"

# ---- 6. self-test ----------------------------------------------------------------------------
step "Checking the packaged app (--self-test)"
report="$root/build/self-test-mac.txt"
set +e
QT_QPA_PLATFORM=offscreen "$app/Contents/MacOS/OneGallery" --self-test "$report"
status=$?
set -e
if [[ $status -ne 0 ]]; then
    if [[ $ffmpeg -eq 0 ]] && grep -q "FAIL ffmpeg" "$report" && ! grep -v "FAIL ffmpeg" "$report" | grep -q "^FAIL"; then
        echo "    (ffmpeg left out on purpose)"
    else
        fail "the packaged app failed its self-test (see above)"
    fi
fi
if [[ $dmg -eq 0 ]]; then
    printf '\n\033[1;32mDone: %s\033[0m\n' "$app"
    exit 0
fi

# ---- 7. disk image -----------------------------------------------------------------------------
step "Disk image"
out="$root/dist/OneGallery-$version-macos-$arch.dmg"
stage="$root/dist/dmg-stage"
rm -rf "$stage"
mkdir -p "$stage"
mv "$app" "$stage/"          # moved, not copied: the app is several hundred MB
ln -s /Applications "$stage/Applications"
rm -f "$out"
hdiutil create -volname "One Gallery" -srcfolder "$stage" -fs HFS+ -format UDZO -imagekey zlib-level=9 -ov "$out" >/dev/null
mv "$stage/One Gallery.app" "$app"
rm -rf "$stage"
printf '\n\033[1;32mDone: %s (%s)\033[0m\n' "$out" "$(du -h "$out" | cut -f1)"
