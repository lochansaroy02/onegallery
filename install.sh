#!/usr/bin/env bash
# Install One Gallery with one command:
#
#   curl -fsSL https://raw.githubusercontent.com/lochansaroy02/onegallery/main/install.sh | bash
#
#   Linux     clones https://github.com/lochansaroy02/onegallery and runs its ./update.sh --install:
#             on Arch/Manjaro that installs the system packages with pacman (system Qt, needed for
#             the KDE global menu), elsewhere a .venv with pip's PySide6; then the launcher, menu
#             entry, icon and the Memories widget in ~/.local. An existing install is updated.
#   macOS     downloads OneGallery-<version>-macos-<arch>.dmg from the latest GitHub release and
#             copies "One Gallery.app" into /Applications
#   Windows   (Git Bash / MSYS2 / Cygwin) downloads OneGallery-<version>-setup.exe from the latest
#             GitHub release and runs the installer for your user (no admin rights)
#
# Options (pass them after "bash -s --", e.g. "curl ... | bash -s -- --restart"):
#   --version vX.Y.Z   macOS/Windows: install that release instead of the latest one
#   --dir PATH         Linux: where to keep the source checkout (default ~/.local/share/onegallery-src)
#   --restart          Linux/macOS: restart One Gallery afterwards if it is running
#
# Your settings, library index, favorites and saved originals live outside the app
# (~/.config/onegallery, ~/.local/share/onegallery, ~/Library/Application Support/One Gallery,
# %APPDATA%\OneGallery) and are never touched.

REPO="lochansaroy02/onegallery"

# everything runs from main(), so a download cut off halfway through can't run half a script
main() {
    set -euo pipefail

    version="" dir="" restart=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --version) [[ $# -ge 2 ]] || fail "--version needs a tag, e.g. --version v0.3.0"
                       version="$2"; shift ;;
            --version=*) version="${1#*=}" ;;
            --dir) [[ $# -ge 2 ]] || fail "--dir needs a path"
                   dir="$2"; shift ;;
            --dir=*) dir="${1#*=}" ;;
            --restart) restart=1 ;;
            -h|--help) usage; exit 0 ;;
            *) fail "Unknown option: $1 (see --help)" ;;
        esac
        shift
    done
    [[ -z "$version" || "$version" == v* ]] || version="v$version"

    command -v curl >/dev/null 2>&1 || fail "curl is required"
    case "$(uname -s)" in
        Linux)                install_linux ;;
        Darwin)               install_macos ;;
        MINGW*|MSYS*|CYGWIN*) install_windows ;;
        *) fail "$(uname -s) is not supported. See https://github.com/$REPO#readme" ;;
    esac
}

usage() {
    cat <<EOF
Install or update One Gallery (Linux, macOS, Windows via Git Bash).

  curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | bash
  curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | bash -s -- [options]

  --version vX.Y.Z   macOS/Windows: install that release instead of the latest one
  --dir PATH         Linux: where to keep the source checkout (default ~/.local/share/onegallery-src)
  --restart          Linux/macOS: restart One Gallery afterwards if it is running
EOF
}

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
fail() { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }

# the script itself arrives on stdin, so prompts (sudo, pacman) must read the terminal
from_tty() {
    if [[ -r /dev/tty ]]; then "$@" </dev/tty; else "$@"; fi
}

tmp="" mountpoint=""
cleanup() {
    [[ -z "$mountpoint" ]] || hdiutil detach -quiet "$mountpoint" >/dev/null 2>&1 || true
    [[ -z "$tmp" ]] || rm -rf "$tmp"
}
make_tmp() {
    tmp="$(mktemp -d 2>/dev/null || mktemp -d -t onegallery)"
    trap cleanup EXIT
}

# ---- Linux: source checkout + update.sh ---------------------------------------------------------
# update.sh already knows how to install and update every kind of Linux install (system packages,
# .venv, launcher, Arch package, renamed LGallery installs, running instance), so this only gets a
# checkout and hands over to it.

# the checkout an existing launcher runs, if any (~/.local/bin/onegallery: exec "<py>" "<dir>/main.py")
installed_checkout() {
    local launcher main
    for launcher in "$HOME/.local/bin/onegallery" "$HOME/.local/bin/lgallery"; do
        [[ -f "$launcher" ]] || continue
        main="$(grep -o '"[^"]*/main\.py"' "$launcher" | head -n 1 | tr -d '"')"
        [[ -n "$main" ]] || continue
        main="$(dirname "$main")"
        if [[ -x "$main/update.sh" && -d "$main/.git" ]]; then
            printf '%s\n' "$main"
            return
        fi
    done
}

install_linux() {
    local here args=(--install)
    [[ -z "$version" ]] || info "--version is for macOS/Windows; Linux installs the newest commit."
    [[ $restart -eq 0 ]] || args+=(--restart)

    if ! command -v git >/dev/null 2>&1; then
        if command -v pacman >/dev/null 2>&1; then
            bold "Installing git (you may be asked for your password)"
            from_tty sudo pacman -S --needed --noconfirm git || fail "could not install git"
        else
            fail "git is required (Debian/Ubuntu: sudo apt install git, Fedora: sudo dnf install git)"
        fi
    fi
    if ! command -v pacman >/dev/null 2>&1; then
        # elsewhere update.sh builds a .venv with pip's PySide6
        command -v python3 >/dev/null 2>&1 || fail "python3 is required (3.11 or newer)"
        python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
            || fail "One Gallery needs Python 3.11 or newer; this system has $(python3 --version 2>&1)"
        python3 -c 'import venv, ensurepip' >/dev/null 2>&1 \
            || fail "Python's venv module is missing (Debian/Ubuntu: sudo apt install python3-venv)"
    fi

    here="$dir"
    [[ -n "$here" ]] || here="$(installed_checkout)"
    [[ -n "$here" ]] || here="${XDG_DATA_HOME:-$HOME/.local/share}/onegallery-src"

    if [[ -d "$here/.git" ]]; then
        bold "Found One Gallery in $here"
        # update.sh pulls first, then refreshes whatever is installed
        from_tty "$here/update.sh" "${args[@]}"
    elif [[ -e "$here" && -n "$(ls -A "$here" 2>/dev/null)" ]]; then
        fail "$here exists and is not a One Gallery checkout; choose another folder with --dir"
    else
        bold "Downloading One Gallery into $here"
        mkdir -p "$(dirname "$here")"
        git clone --quiet "https://github.com/$REPO.git" "$here" || fail "could not clone $REPO (offline?)"
        from_tty "$here/update.sh" --no-pull "${args[@]}"
    fi

    info "Update later by running this command again, or: $here/update.sh"
}

# ---- macOS / Windows: GitHub release ------------------------------------------------------------

# the download URL of the release asset whose name ends with $1
release_asset() {
    local api json url
    if [[ -n "$version" ]]; then
        api="https://api.github.com/repos/$REPO/releases/tags/$version"
    else
        api="https://api.github.com/repos/$REPO/releases/latest"
    fi
    json="$(curl -fsSL -H 'Accept: application/vnd.github+json' "$api")" \
        || fail "could not read the ${version:-latest} release from GitHub (offline, or no such release?)"
    url="$(printf '%s\n' "$json" | grep -o '"browser_download_url": *"[^"]*"' \
           | sed 's/.*"\(https:[^"]*\)"$/\1/' | grep -- "$1\$" | head -n 1 || true)"
    [[ -n "$url" ]] || fail "the ${version:-latest} release has no *$1 download (https://github.com/$REPO/releases)"
    printf '%s\n' "$url"
}

download() {
    bold "Downloading ${1##*/}"
    curl -fL --progress-bar --retry 3 -o "$2" "$1" || fail "download failed: $1"
}

install_macos() {
    local arch url dmg app dest_dir dest running=0
    arch="$(uname -m)"
    # a shell running under Rosetta reports x86_64 on Apple Silicon
    [[ "$(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)" != 1 ]] || arch=arm64
    [[ "$(sw_vers -productVersion | cut -d. -f1)" -ge 13 ]] \
        || fail "One Gallery needs macOS 13 (Ventura) or newer; this Mac has $(sw_vers -productVersion)"
    if [[ "$arch" != arm64 ]]; then
        url="$(release_asset "-macos-$arch.dmg" 2>/dev/null)" \
            || fail "there is no download for Intel Macs yet; build it yourself: https://github.com/$REPO#building-the-mac-app"
    else
        url="$(release_asset "-macos-arm64.dmg")"
    fi

    make_tmp
    dmg="$tmp/${url##*/}"
    download "$url" "$dmg"

    bold "Installing One Gallery"
    mountpoint="$tmp/mnt"
    mkdir -p "$mountpoint"
    hdiutil attach -quiet -nobrowse -readonly -noautoopen -mountpoint "$mountpoint" "$dmg" \
        || fail "could not open the disk image"
    app="$(find "$mountpoint" -maxdepth 1 -name '*.app' | head -n 1)"
    [[ -n "$app" ]] || fail "no app found in the disk image"

    dest_dir=/Applications
    if [[ ! -w "$dest_dir" ]]; then
        dest_dir="$HOME/Applications"
        mkdir -p "$dest_dir"
        info "No write access to /Applications; installing into $dest_dir"
    fi
    dest="$dest_dir/$(basename "$app")"

    if pgrep -xq OneGallery 2>/dev/null; then
        running=1
        info "Closing the running One Gallery"
        osascript -e 'quit app "One Gallery"' >/dev/null 2>&1 || true
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            pgrep -xq OneGallery 2>/dev/null || break
            sleep 0.5
        done
    fi
    rm -rf "$dest"
    ditto "$app" "$dest" || fail "could not copy the app to $dest_dir"
    # not signed with an Apple Developer ID yet: without this Gatekeeper blocks the first start
    xattr -dr com.apple.quarantine "$dest" 2>/dev/null || true
    hdiutil detach -quiet "$mountpoint" >/dev/null 2>&1 || true
    mountpoint=""
    info "Installed $dest"

    if [[ $running -eq 1 && $restart -eq 1 ]]; then
        open "$dest"
        info "One Gallery restarted."
    elif [[ $running -eq 1 ]]; then
        info "Open One Gallery again to use the new version."
    else
        info "Open it from Launchpad or Applications."
    fi
    command -v ffmpeg >/dev/null 2>&1 || info "For video thumbnails install ffmpeg: brew install ffmpeg"
    bold "Install complete."
}

install_windows() {
    local url exe
    url="$(release_asset "-setup.exe")"
    make_tmp
    exe="$tmp/${url##*/}"
    download "$url" "$exe"

    bold "Running the One Gallery installer"
    info "It installs for your user, no admin rights needed. The installer isn't code-signed yet,"
    info "so if SmartScreen warns, choose 'More info' > 'Run anyway'."
    # Inno Setup switches; MSYS2_ARG_CONV_EXCL stops Git Bash from turning /SILENT into a path.
    # A running One Gallery is closed by the installer and not reopened in silent mode.
    MSYS2_ARG_CONV_EXCL='*' "$exe" /SILENT /CURRENTUSER /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS \
        || fail "the installer did not finish"
    info "Open One Gallery from the Start menu."
    bold "Install complete."
}

main "$@"
