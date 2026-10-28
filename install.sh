#!/usr/bin/env bash
# Install One Gallery with one command:
#
#   curl -fsSL https://raw.githubusercontent.com/lochansaroy02/onegallery/main/install.sh | bash
#
#   macOS            downloads OneGallery-<version>-macos-<arch>.dmg from the GitHub release
#                    and copies "One Gallery.app" into /Applications
#   Windows          (Git Bash / MSYS2 / Cygwin) downloads OneGallery-<version>-setup.exe from
#                    the GitHub release and runs the installer (per-user, no admin rights)
#   Arch / Manjaro   installs the 'onegallery' AUR package (with yay or paru, else makepkg)
#   other Linux      clones the source and runs ./update.sh --install (a venv + launcher in ~/.local)
#
# Options (pass them after "bash -s --", e.g. "curl ... | bash -s -- --version v0.3.0"):
#   --version vX.Y.Z   install that release instead of the latest one
#   -h, --help         show this help
#
# Running it again updates an existing install. Your settings, library index and favorites live
# outside the app and are never touched.

# everything is inside main(), so a download cut off halfway through can't run a partial script
main() {
    set -euo pipefail

    local repo="lochansaroy02/onegallery"
    local version="" arg
    while [[ $# -gt 0 ]]; do
        arg="$1"
        case "$arg" in
            --version) [[ $# -ge 2 ]] || fail "--version needs a tag, e.g. --version v0.3.0"
                       version="$2"; shift ;;
            --version=*) version="${arg#*=}" ;;
            -h|--help) usage; exit 0 ;;
            *) fail "unknown option: $arg (see --help)" ;;
        esac
        shift
    done
    if [[ -n "$version" && "$version" != v* ]]; then
        version="v$version"
    fi

    need curl

    case "$(uname -s)" in
        Darwin)                install_macos "$repo" "$version" ;;
        MINGW*|MSYS*|CYGWIN*)  install_windows "$repo" "$version" ;;
        Linux)                 install_linux "$repo" "$version" ;;
        *)                     fail "unsupported system: $(uname -s). See https://github.com/$repo#readme" ;;
    esac
}

usage() {
    cat <<'EOF'
Install One Gallery (macOS, Windows via Git Bash, Linux).

  curl -fsSL https://raw.githubusercontent.com/lochansaroy02/onegallery/main/install.sh | bash
  curl -fsSL .../install.sh | bash -s -- --version v0.3.0

Options:
  --version vX.Y.Z   install that release instead of the latest one
  -h, --help         show this help
EOF
}

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
warn() { printf '\033[33mWarning:\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "'$1' is required but not installed"; }

# prompts (sudo, yay, makepkg) must read the keyboard, not the piped script
tty_in() {
    if [[ -r /dev/tty ]]; then "$@" </dev/tty; else "$@"; fi
}

# ---- GitHub release ---------------------------------------------------------------------------

# Print the download URL of the release asset whose name ends with $3.
release_asset_url() {
    local repo="$1" version="$2" suffix="$3" api json url
    if [[ -n "$version" ]]; then
        api="https://api.github.com/repos/$repo/releases/tags/$version"
    else
        api="https://api.github.com/repos/$repo/releases/latest"
    fi
    json="$(curl -fsSL -H 'Accept: application/vnd.github+json' "$api")" \
        || fail "could not read the release from GitHub ($api). Offline, or rate-limited? Try again later."
    url="$(printf '%s\n' "$json" \
        | grep -o '"browser_download_url": *"[^"]*"' \
        | sed 's/.*"\(https:[^"]*\)"$/\1/' \
        | grep -- "$suffix\$" \
        | head -n 1 || true)"
    [[ -n "$url" ]] || fail "the ${version:-latest} release has no '*$suffix' download. See https://github.com/$repo/releases"
    printf '%s\n' "$url"
}

download() {
    local url="$1" dest="$2"
    bold "Downloading ${url##*/}"
    curl -fL --progress-bar --retry 3 -o "$dest" "$url" || fail "download failed: $url"
}

make_tmpdir() {
    tmp="$(mktemp -d 2>/dev/null || mktemp -d -t onegallery)"
    trap 'cleanup' EXIT
}

cleanup() {
    if [[ -n "${mountpoint:-}" ]]; then
        hdiutil detach -quiet "$mountpoint" >/dev/null 2>&1 || true
    fi
    if [[ -n "${tmp:-}" ]]; then
        rm -rf "$tmp"
    fi
}

# ---- macOS ------------------------------------------------------------------------------------

install_macos() {
    local repo="$1" version="$2" arch major url dmg app dest_dir dest
    need hdiutil
    need ditto

    arch="$(uname -m)"
    # a shell running under Rosetta reports x86_64 on an Apple Silicon Mac
    if [[ "$arch" == x86_64 && "$(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)" == 1 ]]; then
        arch=arm64
    fi
    major="$(sw_vers -productVersion | cut -d. -f1)"
    if [[ "$major" -lt 13 ]]; then
        fail "One Gallery needs macOS 13 (Ventura) or newer; this Mac has $(sw_vers -productVersion)."
    fi

    if [[ "$arch" != arm64 ]]; then
        # releases ship an Apple Silicon build; use an Intel one only if a release has it
        url="$(release_asset_url "$repo" "$version" "-macos-$arch.dmg" 2>/dev/null)" \
            || fail "there is no download for Intel Macs yet. Build it yourself: https://github.com/$repo#building-the-mac-app"
    else
        url="$(release_asset_url "$repo" "$version" "-macos-arm64.dmg")"
    fi

    make_tmpdir
    dmg="$tmp/${url##*/}"
    download "$url" "$dmg"

    bold "Installing One Gallery"
    mountpoint="$tmp/mnt"
    mkdir -p "$mountpoint"
    hdiutil attach -quiet -nobrowse -readonly -noautoopen -mountpoint "$mountpoint" "$dmg" \
        || fail "could not open the disk image"
    app="$(find "$mountpoint" -maxdepth 1 -name '*.app' -print | head -n 1)"
    [[ -n "$app" ]] || fail "no app found in the disk image"

    dest_dir=/Applications
    if [[ ! -w "$dest_dir" ]]; then
        dest_dir="$HOME/Applications"
        mkdir -p "$dest_dir"
        info "No write access to /Applications; installing into $dest_dir"
    fi
    dest="$dest_dir/$(basename "$app")"

    if pgrep -xq OneGallery 2>/dev/null ||pgrep -fq "$dest/Contents/MacOS/" 2>/dev/null; then
        info "Closing the running One Gallery"
        osascript -e 'quit app "One Gallery"' >/dev/null 2>&1 || true
        sleep 2
    fi
    rm -rf "$dest"
    ditto "$app" "$dest" || fail "could not copy the app to $dest_dir"
    # not signed with a Developer ID yet: drop the quarantine flag so Gatekeeper lets it open
    xattr -dr com.apple.quarantine "$dest" 2>/dev/null || true

    hdiutil detach -quiet "$mountpoint" >/dev/null 2>&1 || true
    mountpoint=""

    bold "Installed: $dest"
    info "Open it from Launchpad or Applications (or run: open \"$dest\")."
    if ! command -v ffmpeg >/dev/null 2>&1; then
        info "For video thumbnails install ffmpeg: brew install ffmpeg"
    fi
}

# ---- Windows (Git Bash / MSYS2 / Cygwin) ------------------------------------------------------

install_windows() {
    local repo="$1" version="$2" url exe winexe
    url="$(release_asset_url "$repo" "$version" "-setup.exe")"

    make_tmpdir
    exe="$tmp/${url##*/}"
    download "$url" "$exe"

    bold "Running the One Gallery installer"
    info "Installs for your user (no admin rights). Windows SmartScreen may warn because the"
    info "installer isn't code-signed yet: choose 'More info' > 'Run anyway'."
    winexe="$exe"
    if command -v cygpath >/dev/null 2>&1; then
        winexe="$(cygpath -w "$exe")"
    fi
    # Inno Setup: /SILENT shows only a progress window, /CURRENTUSER skips the admin prompt
    if command -v cmd.exe >/dev/null 2>&1; then
        MSYS2_ARG_CONV_EXCL='*' cmd.exe //c "\"$winexe\" /SILENT /CURRENTUSER /SUPPRESSMSGBOXES /NORESTART" \
            || fail "the installer did not finish"
    else
        "$exe" /SILENT /CURRENTUSER /SUPPRESSMSGBOXES /NORESTART || fail "the installer did not finish"
    fi

    bold "Installed."
    info "Open One Gallery from the Start menu."
}

# ---- Linux ------------------------------------------------------------------------------------

install_linux() {
    local repo="$1" version="$2"
    if [[ -n "$version" ]]; then
        warn "--version is ignored on Linux: it installs the current package/source"
    fi
    if command -v pacman >/dev/null 2>&1; then
        install_arch
    else
        install_from_source "$repo"
    fi
}

install_arch() {
    local helper="" h build
    for h in yay paru; do
        if command -v "$h" >/dev/null 2>&1; then helper="$h"; break; fi
    done

    if [[ -n "$helper" ]]; then
        bold "Installing the 'onegallery' AUR package with $helper"
        tty_in "$helper" -S --needed onegallery || fail "$helper could not install onegallery"
    else
        bold "Building the 'onegallery' AUR package with makepkg"
        info "(you may be asked for your password)"
        tty_in sudo pacman -S --needed base-devel git || fail "could not install base-devel and git"
        make_tmpdir
        build="$tmp/onegallery"
        git clone --depth 1 https://aur.archlinux.org/onegallery.git "$build" \
            || fail "could not download the AUR package"
        ( cd "$build" && tty_in makepkg -si --needed ) || fail "makepkg failed"
    fi

    bold "Installed."
    info "One Gallery is in the application launcher (command: onegallery)."
    info "Updates now come with your normal system update ($([[ -n "$helper" ]] && echo "$helper -Syu" || echo "rerun this script"))."
}

install_from_source() {
    local repo="$1" src="${XDG_DATA_HOME:-$HOME/.local/share}/onegallery-app"
    need git
    need python3
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
        || fail "One Gallery needs Python 3.11 or newer; this system has $(python3 --version 2>&1)"
    python3 -c 'import venv, ensurepip' >/dev/null 2>&1 \
        || fail "Python's venv module is missing. On Debian/Ubuntu: sudo apt install python3-venv"

    if [[ -d "$src/.git" ]]; then
        bold "Updating One Gallery in $src"
        "$src/update.sh" --install
    else
        bold "Downloading One Gallery into $src"
        git clone --depth 1 "https://github.com/$repo.git" "$src" || fail "could not clone $repo"
        "$src/update.sh" --no-pull --install
    fi

    bold "Installed."
    info "One Gallery is in the application launcher (command: ~/.local/bin/onegallery)."
    info "Update later by running this script again, or: $src/update.sh"
}

main "$@"
