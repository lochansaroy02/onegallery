# One Gallery

One Gallery is a desktop photo and video gallery for Arch-based Linux (Manjaro) on KDE Plasma, styled after Samsung One UI's Gallery app. You choose the folders it shows, including folders on other drives. It indexes them in the background and lists your pictures and videos newest first, grouped by day, the way a phone gallery does. It also runs on [Windows](#windows) and [macOS](#macos).

> **Renamed from LGallery.** Your settings, library, favorites, private album and saved originals move over by themselves the first time One Gallery starts (`~/.config/lgallery` → `~/.config/onegallery`, and the same for `~/.local/share` and `~/.cache`; on Windows `%APPDATA%\LGallery` → `%APPDATA%\OneGallery` and `%LOCALAPPDATA%\LGallery` → `%LOCALAPPDATA%\OneGallery`). The command is now `onegallery`. `./update.sh` replaces an old install.

- **Pictures tab:** day headers that stay visible while you scroll ("Today", "Yesterday", "Fri, Oct 23"), a title that shrinks as you scroll, a fast-scroll handle with a month bubble, and **Ctrl + mouse wheel** or **Ctrl +/-** to change the number of columns.
- **Videos:** videos sit among your pictures in date order, with a ▶ length badge. The **Videos tab** lists only videos. Opening a video plays it straight away, **muted**, with a mute button. **Play video** opens the built-in player with sound (see [Videos](#videos)).
- **Albums tab:** one album per watched folder, or one per sub-folder (a setting), plus **Favorites** and **Videos**.
- **Private album:** password-protected and encrypted. Pictures and videos moved in disappear from their folders and from the rest of One Gallery. See [Private album](#private-album).
- **Collections tab:**
  - **Stories:** slideshows of pictures taken around today's date in earlier years.
  - **Places:** pictures grouped by town and country, from GPS.
  - **People:** on-device face grouping, with naming, merging and hiding.
- **Folders tab:** add or remove watched folders and rescan. Removing a folder **never deletes files**.
- **Phone sync:** new photos and videos from your Android phone arrive over Wi-Fi through KDE Connect, with no cable and no cloud. See [Phone sync](#phone-sync-kde-connect).
- **Desktop widget:** *One Gallery Memories* puts a photo frame on your Plasma desktop or panel. It shows pictures from this day in earlier years, your favorites, your latest photos, or any folders you choose. It can cross-fade, or animate like a Windows Photos live tile. See [Memories widget](#memories-widget-kde-plasma).
- **Selection mode:** right-click or long-press a picture, or tick a day header to select the whole day. Actions: Delete (to the trash), Share, Open with, Copy path, Show in folder.
- **Share menu:** the same options as Dolphin's *Share* submenu: Copy to Clipboard, KDE Connect, Bluetooth, e-mail, Telegram, Imgur, Nextcloud, Google Drive and anything else your KDE has installed.
- **Viewer:** arrow keys or swipe to move between pictures, wheel or double-click or pinch to zoom, drag to pan, and a Details panel. The ⋮ menu offers:
  - **Set as ▸** Wallpaper, Lock screen, or both (KDE Plasma);
  - **Print…** to any printer, or **Save as PDF**, with a live page preview;
  - Open with, Show in folder, Copy picture / path, and Revert to original.
- **Photo editor:** Transform (crop with aspect presets, rotate, flip, straighten), 9 Filters, and Adjust (brightness, exposure, contrast, highlights, shadows, saturation, warmth, tint, sharpness, vignette). It has undo/redo and hold-to-compare, and you can **Save**, **Save as copy** or **Revert to original**.
- **Default image viewer:** open any picture from Dolphin in One Gallery's viewer. Left/right moves through that folder, and the folder is **not** added to your library.
- **Search:** by file name, folder or date (`2025`, `October`, `oct 2024`, `Screenshot`).
- **Live updates** (needs watchdog). Folders on unmounted drives are kept and marked *unavailable* instead of being removed.
- **Themes:** light and dark. By default it follows your KDE colour scheme, and you can override that in Settings.
- **Colour style** (**Settings → Appearance**, or **View ▸ Colour Style**):
  - **Black & white** (the default): One UI's pure white / pure black surfaces, with the accent colour only on highlights.
  - **Material You**: like Android 12+, the whole palette is generated from the accent colour. Backgrounds, cards, the bottom bar, text, dividers and grid placeholders take soft tones of its hue, and the accent itself becomes a deeper tone in light mode and a pastel one in dark mode.
  - Layout and components are the same in both; only the colours change.
- **Navigation bar** (**Settings → Appearance**, or **View ▸ Navigation Bar**): **Solid** (the default), or Liquid Glass like iOS 26:
  - **Frosted:** the pictures behind the bar are blurred under a milky layer of the bar's colour.
  - **Clear:** the bar is see-through, with a light veil for legibility.
  - Both bend what's behind them at the rim like thick glass, with a slight colour fringe and a highlight along the top edge.
  - Glass needs GPU rendering. Where Qt draws in software (some virtual machines, `QT_QUICK_BACKEND=software`), the bar stays solid.
  - The shader is `qml/shaders/liquidglass.frag`. Run `qml/shaders/build.sh` after editing it; the compiled `.qsb` is committed.
- **Accent colour:** by default One Gallery uses **KDE's accent colour** (*System Settings → Colors & Themes → Colors → Accent color*, including *From wallpaper*), and it updates live when you change it. **Settings → Appearance → Accent colour** (or **View ▸ Accent Colour**) offers 12 other colours or any custom colour.

## Quick install

One command installs One Gallery on Linux, macOS and Windows (in Git Bash):

```bash
curl -fsSL https://raw.githubusercontent.com/lochansaroy02/onegallery/main/install.sh | bash
```

- **Linux:** clones this repository into `~/.local/share/onegallery-src` and runs `./update.sh --install` there (see [Install from source](#install-from-source-on-arch--manjaro)). If One Gallery is already installed, it updates that install instead.
- **macOS:** downloads the `.dmg` from the latest [release](https://github.com/lochansaroy02/onegallery/releases) and copies **One Gallery** into Applications.
- **Windows:** downloads the `-setup.exe` from the latest release and runs it for your user.

Options go after `bash -s --`, e.g. `curl … | bash -s -- --restart`: `--version v0.3.0` (macOS/Windows: a specific release), `--dir PATH` (Linux: where the checkout lives), `--restart` (Linux/macOS: reopen a running One Gallery).

Optional extras on Arch / Manjaro: `sudo pacman -S python-pillow-heif python-opencv python-watchdog purpose kdeconnect sshfs` (HEIC photos, People, live updates, the KDE share menu, phone sync).

## Windows

One Gallery also runs on Windows 10 (1809 or newer) and 11, 64-bit.

**Install:** download `OneGallery-<version>-setup.exe` from the [Releases page](https://github.com/lochansaroy02/onegallery/releases) and run it.
- No admin rights are needed: it installs for your user, or for everyone if you choose that on the first page.
- It adds One Gallery to the Start menu, and optionally to the desktop.
- It adds One Gallery to *Open with* for pictures and videos and to **Settings → Apps → Default apps**. Pick it there to open pictures from Explorer in One Gallery.
- The installer isn't code-signed yet, so Windows SmartScreen may warn the first time. Choose **More info → Run anyway**.
- Uninstall from **Settings → Apps**. Your settings and index stay in `%APPDATA%\OneGallery` and `%LOCALAPPDATA%\OneGallery`; delete those folders to remove everything.

**On Windows:**
- *Delete* moves files to the Recycle Bin.
- *Show in folder* opens Explorer with the file selected.
- *Open with* shows Windows' own app chooser.
- *Set as* sets the desktop wallpaper and the lock screen. Organisations can lock the lock screen through policy.
- Video thumbnails and frame capture use the bundled ffmpeg.
- The accent colour follows Windows' accent colour.
- KDE-only parts (the global menu and the KDE share menu) are left out. *Share* offers *Copy to Clipboard*.

### Building the Windows installer

**On GitHub (no Windows PC needed):** the workflow in `.github/workflows/windows.yml` builds the installer on GitHub's Windows machines.
- Push a version tag (`git tag v0.3.0 && git push origin v0.3.0`) and the installer is attached to that release.
- Or run it by hand: **Actions → Windows build → Run workflow**. It builds without a release; download the installer from the run's *Artifacts*.

**On a Windows PC:**

```powershell
winget install Python.Python.3.13 JRSoftware.InnoSetup Git.Git
git clone https://github.com/lochansaroy02/onegallery.git
cd onegallery
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
```

Run `build.ps1` again later to rebuild; the downloads are reused.

The result is `dist\OneGallery-<version>-setup.exe`, plus the unpacked app in `dist\OneGallery\OneGallery.exe`. The script:
1. makes `build\venv` and installs the Python packages;
2. downloads ffmpeg (LGPL build) for video thumbnails;
3. runs the unit tests;
4. bundles everything with PyInstaller (`packaging/windows/onegallery.spec`);
5. checks the bundled app with `OneGallery.exe --self-test`: interface, video playback, printing and ffmpeg;
6. builds the installer with Inno Setup (`packaging/windows/onegallery.iss`).

Options: `-NoFaces` leaves out OpenCV (People), which saves about 40 MB. `-NoFfmpeg` leaves out video thumbnails. `-SkipTests` skips the unit tests, and `-NoInstaller` stops after `OneGallery.exe`.

The app icon is `packaging/windows/onegallery.ico`. It's made from `packaging/icon.svg` by `python packaging/windows/make_icon.py`.

## macOS

One Gallery also runs on macOS 13 (Ventura) or newer. The download is for Apple Silicon Macs (M1 and later); on an Intel Mac, [build it yourself](#building-the-mac-app).

**Install:**
1. Download `OneGallery-<version>-macos-arm64.dmg` from the [Releases page](https://github.com/lochansaroy02/onegallery/releases).
2. Open the `.dmg` and drag **One Gallery** onto the **Applications** folder.
3. Eject the disk image and open One Gallery from Applications or Launchpad.
4. The app isn't signed with an Apple Developer ID yet, so the first time macOS says it can't check it for malware. Click **Done** (not *Move to Trash*), then:
   - **macOS 15 (Sequoia) and newer:** open **System Settings → Privacy & Security**, scroll down to *"One Gallery" was blocked*, click **Open Anyway**, and confirm with your password.
   - **macOS 13 and 14:** in Finder, right-click (or Control-click) One Gallery in Applications, choose **Open**, then **Open** again.
   - **Or, in Terminal:** `xattr -dr com.apple.quarantine "/Applications/One Gallery.app"`

   You only need to do this once.
5. **Video thumbnails** need ffmpeg, which this build doesn't include. Install it with [Homebrew](https://brew.sh): `brew install ffmpeg`. One Gallery finds it by itself. Videos play without it.

**Open pictures from Finder in One Gallery:** open **Settings → Default image viewer → Set as default**. One Gallery must be in Applications and opened from there once. You can also right-click a picture in Finder and choose **Open With → One Gallery**.

**Uninstall:** drag One Gallery from Applications to the Trash. Your settings and index stay in `~/Library/Application Support/One Gallery` and `~/Library/Caches/One Gallery`; delete those folders to remove everything.

**On macOS:**
- *Delete* moves files to the Trash.
- *Show in folder* opens Finder with the file selected.
- *Open with* lists the Mac apps that open the file, like Finder does.
- *Set as* sets the desktop picture. The lock screen shows the desktop picture, so there's no separate lock-screen option. The first time, macOS asks to let One Gallery control System Events; allow it.
- The menus are in the Mac menu bar.
- The accent colour follows the accent colour in System Settings.
- *Share* offers *Copy to Clipboard*.

### Building the Mac app

On a Mac with Python 3.11 or newer (`brew install python@3.13`):

```bash
git clone https://github.com/lochansaroy02/onegallery.git
cd onegallery
packaging/macos/build.sh
```

The result is `dist/OneGallery-<version>-macos-<arch>.dmg`, plus the app itself in `dist/One Gallery.app`. It builds for the Mac it runs on: `arm64` on Apple Silicon, `x86_64` on Intel. The script:
1. makes `build/venv-mac` and installs the Python packages;
2. downloads ffmpeg and ffprobe for video thumbnails;
3. runs the unit tests;
4. bundles everything with PyInstaller (`packaging/macos/onegallery.spec`);
5. signs the app ad hoc (there's no Apple Developer ID, hence the one-time *Open Anyway*);
6. checks the bundled app with `--self-test`: interface, video playback, printing, private album and ffmpeg;
7. packs it into a `.dmg` with a shortcut to Applications.

Options: `--no-faces` leaves out OpenCV (People), `--no-ffmpeg` leaves out video thumbnails, `--skip-tests` skips the unit tests, and `--no-dmg` stops after the app. Set `BUILD_PYTHON=/path/to/python` to build with an existing environment instead of making `build/venv-mac` (it saves about 1 GB). The build needs about 3 GB of free disk space.

The app icon is `packaging/macos/onegallery.icns`. It's made from `packaging/icon.svg` by `python packaging/macos/make_icns.py`.

## Install from source on Arch / Manjaro

There are two ways to install One Gallery as a KDE app from a checkout. Both add **One Gallery** to the application launcher (under *Graphics*) with its own icon, so you can pin it to the panel or task manager like any other app.

| | Option A: user install | Option B: Arch package |
| --- | --- | --- |
| Needs root | No | Yes (pacman) |
| Runs from | your checkout folder (`.venv`) | `/usr/share/onegallery` |
| Update | `git pull` | `git pull` + `makepkg -si` again |
| Best for | trying it out, development | everyday use |

### 1. Get the code

```bash
sudo pacman -S --needed git
git clone https://github.com/lochansaroy02/onegallery.git
cd onegallery
```

### Option A: user install (recommended)

From the project folder, one command does everything:

```bash
./update.sh --install
```

It:
1. installs the system packages with pacman: `pyside6` (the system Qt bindings), `python-pillow`, `python-cryptography` (private album), `qt6-declarative`, `qt6-svg`, `qt6-imageformats`, `qt6-multimedia`, `qt6-multimedia-ffmpeg` and `ffmpeg` (video playback and video thumbnails) and, when available, `python-watchdog`, `python-send2trash`, `purpose`, `plasma-integration` and `xdg-utils`;
2. creates `.venv` on top of them (`--system-site-packages`) and adds `pillow-heif` from PyPI for HEIC photos;
3. installs the launcher, menu entry and icon (`~/.local/bin/onegallery`, `~/.local/share/applications/onegallery.desktop`).

One Gallery runs on **Manjaro's own Qt**, not on pip's bundled copy. That is what makes the **KDE global menu**, native KDE file dialogs and the KDE theme work, and it saves about 1 GB of downloads.

Open the application launcher and search for **One Gallery**. If it doesn't show up right away, run `kbuildsycoca6` or log out and back in. You can also start it from a terminal with `onegallery` (if `~/.local/bin` is on your `PATH`).

> The launcher points to this folder. If you move or rename the project folder, run `./update.sh --no-pull` again.

**Update:** `./update.sh` (see [Updating](#updating)).
**Uninstall:** `./packaging/install-user.sh --uninstall`

<details>
<summary>Other distributions / manual setup with pip</summary>

Without pacman, `update.sh` falls back to pip's PySide6. Everything works except the global menu on Wayland, and you use the ⋮ menu instead.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./packaging/install-user.sh
```
</details>

### Option B: system-wide Arch package

This builds a real pacman package from your checkout, using the distro's Python packages (no venv):

```bash
sudo pacman -S --needed base-devel pyside6 python-pillow python-cryptography qt6-declarative qt6-svg qt6-imageformats \
    qt6-multimedia qt6-multimedia-ffmpeg ffmpeg
sudo pacman -S --needed python-watchdog python-send2trash   # optional: live updates, trash
cd packaging
makepkg -si
```

This installs `/usr/bin/onegallery`, `/usr/share/onegallery/`, `/usr/share/applications/onegallery.desktop` and the icon. **One Gallery** then appears in the launcher for all users. HEIC support is optional: `sudo pacman -S python-pillow-heif`.

**Update:** `./update.sh` (see [Updating](#updating)).
**Uninstall:** `sudo pacman -R onegallery`

### Updating

From the project folder, run:

```bash
./update.sh
```

It pulls the latest commits from GitHub, shows what changed, and updates whichever install you have:

- **User install (option A):** installs any missing system packages with pacman, then refreshes the launcher, menu entry and icon. An older install that used pip's PySide6 is switched to Manjaro's `pyside6` automatically (needed for the global menu). If an Arch Python upgrade broke `.venv`, it is recreated.
- **Arch package (option B):** rebuilds and reinstalls the package with `makepkg` (asks for your password).
- **Not installed yet:** sets up `.venv`; add `--install` to also put One Gallery in the launcher.

| Option | What it does |
| --- | --- |
| `--restart` | restart One Gallery afterwards if it is open (otherwise just close and reopen it) |
| `--no-pull` | skip `git pull`, only reinstall from the current folder |
| `--install` | install the launcher if One Gallery isn't installed yet |

The script stops without changing anything if you have edited tracked files locally (commit them or `git stash` first). It also checks that the new version starts before reinstalling a package. Your settings, library, favorites and saved originals are never touched by an update.

### Make One Gallery your image viewer (open pictures from Dolphin)

After installing with option A or B, choose one of these:

- **Everything at once:** open One Gallery, go to **Settings → Default app → Set as default**. One Gallery becomes the default for JPEG, PNG, WebP, GIF, BMP and TIFF (and HEIC/HEIF if supported).
- **One format at a time, from Dolphin:** right-click a picture, choose **Properties**, click the **⚙ File Type Options** button next to the type, select **One Gallery** in the application list, click **Move Up** to put it first, then **Apply**. If One Gallery isn't listed, click **Add…** and choose **One Gallery** (Graphics).
- **Just once:** right-click a picture, choose **Open With**, then **One Gallery**.

Then double-clicking a picture in Dolphin (or any file manager):

- opens it directly in One Gallery's full-screen viewer;
- lets you use **← / →** (or swipe) to go through the other pictures in **that folder**, in the same natural name order as Dolphin (`IMG_2` before `IMG_10`);
- does **not** add that folder to the library. Nothing is indexed, and your Pictures/Albums tabs stay unchanged;
- if One Gallery is already open, shows the picture in that window instead of starting a second copy.

Edit, Share, Delete, Details and Show in folder all work there. Favorites are only for pictures in your library, so the heart is hidden for other pictures. **Esc** / **←** closes the viewer and quits, like a photo viewer. Use **⋮ → Open One Gallery** to switch to the full library instead.

From a terminal, `onegallery ~/Downloads/photo.jpg` does the same. If you select several pictures and open them together, navigation is limited to just those files.

To stop using One Gallery as the default, pick another app in Dolphin's **File Type Options**, or in **System Settings → Default Applications** / **File Associations**.

### After installing (optional)

- **Pin to the panel:** start One Gallery, right-click its icon in the task manager, and choose **Pin to Task Manager**.
- **Your data survives reinstalls:** uninstalling either way leaves your settings, index and thumbnail cache in place (see [Where data lives](#where-data-lives)). Delete those folders for a clean slate.

## Using it

1. On first launch the gallery is empty. Click **Add folder** (or **Add Pictures** for `~/Pictures`), or press **Ctrl+O**.
2. Scanning runs in the background, and pictures appear while it works. Later rescans only read files that changed.
3. To add folders on other drives, mount the drive and add the folder. If the drive is unmounted later, its pictures stay in the gallery, greyed out with a ⚠ mark, and become available again when you remount it. The app checks for mounts every 10 seconds.
4. To remove a folder, open the **Folders** tab and click ✕ on the folder. Its pictures disappear from the gallery, and the files are left untouched.
5. To skip some sub-folders (for example `Screenshots` or a work folder), open the **Folders** tab, click the **folder-minus** button on a watched folder (or use **File ▸ Exclude Sub-folders**), then untick the sub-folders to skip.
   - You can open folders to go deeper; the path at the top takes you back up.
   - An unticked folder is skipped with everything inside it. Its pictures leave the gallery, and the files stay on disk.
   - Live updates ignore excluded folders too.
   - Tick a folder again to bring its pictures back.
   - A folder inside an excluded area can still be added as its own watched folder.

### Videos

- **Formats:** mp4, m4v, mov, mkv, webm, avi, 3gp, mts/m2ts, wmv, ogv, mpg/mpeg.
- **Date:** the recording date stored in the video, otherwise the file's modification time. Videos are sorted with your photos by that date.
- **Thumbnails and length:** made with `ffmpeg` / `ffprobe` (installed by `update.sh`). Without ffmpeg, MP4/MOV/3GP dates, sizes and lengths are still read from the file, and thumbnails show a placeholder. Real thumbnails appear once ffmpeg is installed.
- **In the viewer:** a video starts playing on its own, muted and looping. The **🔇 button** (or **M**) turns the sound on or off. The **📷 button** next to it (or **S**) captures the frame on screen. **Play video** (or **Enter**, or a double-click) opens the player and continues from the same moment. Back in the viewer, the preview continues from where the player stopped.
- **The player:**
  - seek bar with a time bubble while you drag or hover;
  - play/pause, back and forward 10 seconds, volume slider, mute;
  - playback speed from 0.25× to 2×, loop, full screen;
  - controls hide while the video plays and come back when you move the mouse;
  - when a codec isn't supported, the player says so and offers *Open in default app*.
- **Capture frame** (📷, **S**, in the viewer and the player) saves the exact frame at the video's full resolution as a JPEG next to the video (`clip_frame_01-23-456.jpg`), or in `~/Pictures/Screenshots` when the video's folder is read-only. The picture is dated at that moment of the recording, so it sits right beside the video in your gallery. Needs ffmpeg.
- **Playback** uses Qt Multimedia with its FFmpeg backend (`qt6-multimedia`, `qt6-multimedia-ffmpeg`). The file is played from disk as it is read, never loaded into memory. If Qt Multimedia is missing, the rest of One Gallery still works, and videos open in your default player.
- Videos are skipped by People (faces), Stories and the photo editor. They do count for Places when they carry GPS.

### Private album

Keep pictures and videos behind a password, like Samsung's Secure Folder or Google Photos' Locked Folder.

- **Moving items in:**
  - Select items and tap **Private** in the selection bar.
  - Or use **⋮ / right-click → Move to private album**, or press **Ctrl+Shift+H**.
  - The first time, you set a password (at least 6 characters, typed twice).
- **Opening it:**
  - From **Albums → Private album**, **View ▸ Private Album**, or **Settings → Private album**.
  - Inside, it's the usual date grid and viewer.
  - To get a file back, use **Move out**. It returns to its original folder, or to `~/Pictures/Restored from private album` if that folder is gone.
  - **Delete** removes a file for good; it doesn't go to the trash.
- **Locking:**
  - Tap the 🔒 button, leave the album, or minimise the window, and it locks.
  - If you only unlocked it to move something in, it locks again straight away.
  - After 5 wrong passwords in a row, unlocking pauses for 30 seconds.
- **What "protected" means:**
  - Files are encrypted with AES-256-GCM, and their names and dates are encrypted too.
  - The key is unlocked by your password through scrypt.
  - The originals are deleted, and so is everything One Gallery kept about them: index entries, cached thumbnails, face crops, the editor's backup and the *Open Recent* entry.
  - The encrypted files live in `~/.local/share/onegallery/private/` (on Windows, `%LOCALAPPDATA%\OneGallery\private`).
  - Videos are decrypted to a private temporary folder while they play: `$XDG_RUNTIME_DIR`, which is in RAM on most Linux systems. They're deleted on lock and on quit.
- **Forgotten password:** there is no recovery. **Settings → Private album → Delete private album** removes it and everything in it, so you can start again.
- **Limits:**
  - Deleting the original doesn't wipe the disk blocks it used, so tools that recover deleted files may still find older copies.
  - Backups or cloud sync that already copied the originals keep their copies.
  - It needs `python-cryptography`, which `update.sh` installs.

### Phone sync (KDE Connect)

One Gallery imports new photos and videos from your Android phone over Wi-Fi. It uses KDE Connect, which most Plasma desktops already have. Nothing goes through the cloud.

**Set up, once:**
1. Install KDE Connect and sshfs on the computer: `sudo pacman -S kdeconnect sshfs`. Install **KDE Connect** on the phone from Google Play or F-Droid.
2. Pair the phone with the computer in KDE Connect (both on the same Wi-Fi).
3. On the phone, open KDE Connect, tap the computer, and in its plugin settings allow **Filesystem expose** and choose the storage to share. On the computer, keep the **Remote filesystem browser** plugin turned on for the phone (*System Settings → KDE Connect → the phone*).
4. In One Gallery, open the **Folders** tab. Under **Phones** the phone shows up as *connected*. Choose:
   - **Import all:** copies every photo and video that's on the phone now.
   - **Only new ones:** remembers what's on the phone now and imports only what you take from now on.

**After that:**
- While the phone is connected, new photos are imported by themselves (every 10 minutes at most). Turn this off with the switch on the phone's card; **Sync now** imports straight away, and **Stop** stops a running import.
- Photos go to `~/Pictures/Phone/<phone name>/`, in `Camera` and `Screenshots` folders, with their original dates. That folder is added to the gallery by itself (unless `~/Pictures` is already in it).
- Imported from: everything in the phone's `DCIM` folder (the camera), and `DCIM/Screenshots` and `Pictures/Screenshots` unless you turn off **Settings → Phones → Import screenshots**. SD cards are included. Hidden and trashed files are skipped.
- Each file is imported **once**. Deleting a picture on the computer doesn't bring it back next time, and photos are never deleted or changed on the phone.
- **✕ (Stop syncing)** forgets the phone. The photos already imported stay.
- The **folder** button opens the phone's folder in Dolphin.
- Phone sync needs Linux with KDE Connect running; the **Phones** section is hidden otherwise.

### Collections: Stories, Places and People

The **Collections** tab (third in the bottom bar, `Ctrl+3`) has three sections.

**Stories.** Every day, One Gallery looks for pictures you took **within 3 days of today's date in earlier years**: "1 year ago", "3 years ago", and so on. It prefers favorites, skips burst duplicates, and shows up to 24 pictures per story.
- Click a story to play it full screen, with slow zoom-and-pan and crossfades.
- Click the right side to go forward and the left side to go back.
- Press and hold (or press Space) to pause, and Esc to close.
- The 🖼 button opens the current picture in the viewer.
- Stories are also in the menu under **Go ▸ Stories**.

**Places.** Pictures with GPS in their EXIF data (most phones add it) are grouped by **town and country**.
- The first time, click **Download** to fetch the GeoNames town list (3 MB, CC BY 4.0). After that, lookups work **offline**; nothing is sent anywhere per photo.
- Photos taken more than 60 km from any town are labelled with the country.
- **See all** lists every place by country, and each place opens as an album.

**People.** One Gallery groups pictures by face, like Google Photos, but **entirely on this computer**.
- It's off until you click **Turn on** (or use **Settings → Collections**). The first time, it downloads two small open models from OpenCV's model zoo (YuNet and SFace, 38 MB in total, checksum-verified).
- It then scans your library in the background; progress shows in the People section. New pictures are scanned automatically.
- A person appears once their face is found in **at least 3 pictures**.
- Open a person to **name** them (✏), combine two groups of the same person (**Same person as…**), or **hide** someone. Hidden people can be shown again from the People page (👁).
- Only face boxes and face "fingerprints" (embeddings) are stored, in the index. **Settings → Collections → Delete face data** removes them all.
- People needs OpenCV (`opencv-python-headless`), which `./update.sh` installs. For the Arch package, install `python-opencv`.

### Memories widget (KDE Plasma)

**One Gallery Memories** is a Plasma 6 widget: a photo frame that cross-fades through your pictures with a slow zoom and shows when each was taken.

**Add it:** right-click the desktop (or a panel) → **Add Widgets…** → search for **One Gallery Memories** → drag it onto the desktop.
- `packaging/install-user.sh` (also run by `./update.sh`) and the Arch package install it.
- If it isn't listed right after installing, log out and back in, or run `plasmashell --replace &`. Do the same after an update to load the new version.

**What it shows** (right-click the widget → **Configure One Gallery Memories…**):
- **Memories** (the default): the same pictures as today's [Stories](#collections-stories-places-and-people). On days without memories it shows favorites, then your most recent pictures.
- **Favorites:** a different set of up to 40 favorites each day.
- **Recent pictures:** your 40 newest pictures.
- **Pictures from folders:** click **Add Folder…** and pick any folders, including ones on other drives and ones that aren't in One Gallery. Sub-folders are included. Each day the widget picks a new random set of up to 60 pictures per folder, and with several folders it takes one picture from each in turn. A folder on an unplugged drive just shows nothing until the drive is back.

**Animation:**
- **Cross-fade** (the default): one picture fades into the next, with a slow zoom.
- **Live tile: slide up:** like the Windows Photos live tile, the new picture slides up and pushes the old one out, along with its caption. Going back slides down.
- **Live tile: flip mosaic:** like Windows Phone's photo tiles. The widget becomes a mosaic: a large picture with two small ones beside it on a wide widget, or with five small ones around it on a square widget. Every few seconds one tile flips over in 3D to a picture that isn't already showing. Choose how often under **Flip a tile every**; 4–8 seconds looks lively.

You can also set how long each picture stays, choose between filling the frame and fitting the whole picture, and turn off the slow zoom or the caption.

**Using it:**
- Click a picture (in the mosaic, any tile) to open it in One Gallery's viewer.
- Hover to show ‹ › buttons, or scroll the mouse wheel to move between pictures. The slideshow pauses while the pointer is over it.
- The widget's edit toolbar has **Show background**. Turn it off for a frameless, rounded photo.
- In a panel, the widget shows a small picture; click it to open the frame.

**How it works:** the widget doesn't read your library itself. One Gallery writes the pictures it needs to `~/.cache/onegallery/widget/`:
- `feed.json` lists them.
- Each picture is saved as an upright copy of at most 1280 px, so HEIC photos and pictures on unplugged drives still work.
- While One Gallery is open, it updates that folder when your library or favorites change, but only if the widget is on your desktop.
- When One Gallery isn't running, the widget runs `onegallery --widget-feed` itself once a day. That command builds the feed without opening a window.
- Pictures from chosen folders are prepared the same way: the widget passes them as `--folder DIR` when you add a folder, and the app reads the folders from the widget's settings.

### Editing photos

Open a picture and click the **pencil** (or press **E**).

| Tab | What it does |
| --- | --- |
| **Transform** | Drag the corners or edges of the crop box, or pick an aspect ratio (Free, Original, 1:1, 4:3, 3:4, 16:9, 9:16). Rotate 90°, flip, and straighten by up to ±45°. |
| **Filters** | Vivid, Bright, Warm, Cool, Dramatic, Fade, Vintage, Mono and Noir, with an intensity slider. |
| **Adjust** | Pick a tool and drag the slider. Double-click the slider or the tool to reset it. A blue dot marks tools you've changed. |

- **Undo / Redo:** the arrows at the top left, or **Ctrl+Z** / **Ctrl+Shift+Z**.
- **Compare:** hold the split-square button at the bottom right of the picture (or hold **\\**) to see the original.
- **Reset:** discards all unsaved edits. **✕** or **Esc** closes the editor and asks before throwing changes away.

**Saving.** There are two ways to save, and an edited picture keeps its original date, so it stays in the same place in your timeline.

- **Save** (**Ctrl+S**) overwrites the picture with your edits. Before the **first** save of a file, One Gallery copies the untouched original to `~/.local/share/onegallery/originals/`.
- **Save as copy** (**Ctrl+Shift+S**) writes a new file next to the original, for example `IMG_1234_edited.jpg`, and leaves the original untouched.

EXIF data (camera, date, GPS) and colour profiles are kept, and the orientation tag is reset because the pixels are already upright.

**Reverting.** After a **Save**, you can always go back to the original, even weeks later:

- in the viewer, open the **⋮** menu and choose **Revert to original**, or
- in the editor, click **Revert**. It appears when the picture has a saved original and has no unsaved edits.

Reverting restores the original file exactly (byte for byte, including its modification time) and deletes the backup. To reclaim disk space, **Settings → Storage → Saved originals → Delete** removes all backups, after which edited pictures can no longer be reverted.

You can edit and save JPEG, PNG, WebP, TIFF, BMP and static GIF files, plus HEIC when pillow-heif has an encoder. Animated GIF/WebP files can't be edited.

### Menus: KDE global menu and the ⋮ menu

One Gallery has a full application menu: **File, Edit, View, Go, Settings, Help**.

- **With the Global Menu widget** (Plasma panel → *Add Widgets → Global Menu*), the menu appears in your panel like on macOS. It works on Wayland and X11.
- **Without it,** the same menu is behind the **⋮** button at the top right of the Pictures, Albums and Folders tabs.

Items enable themselves from context: a picture open in the viewer, a selection, or the editor.

| Menu | What's in it |
| --- | --- |
| **File** | Add Folder…, Open Picture… (view a picture without adding its folder), **Open Recent ▸**, Save / Save as Copy (in the editor), **Share ▸** (KDE share targets), Open With…, Show in Folder, Rescan Folders, Move to Trash, Quit |
| **Edit** | Undo / Redo (editor), Select All, Deselect All, Copy Picture, Copy Path, Edit Picture…, **Rotate ▸** Left / Right (saved, revertible), Add to / Remove from Favorites, Revert to Original |
| **View** | Pictures / Albums / Folders, **Thumbnail Size ▸** (bigger, smaller, 2–12 columns), **Sort ▸** Newest / Oldest First, **Theme ▸** System / Light / Dark, Albums per Sub-folder, Zoom In / Out / Fit, Show Details, Full Screen |
| **Go** | Back, Previous / Next / First / Last Picture, Today, **Jump to Year ▸**, **Albums ▸** (every album), Favorites, Search |
| **Settings** | Settings…, Live Updates, Set as Default Image Viewer, Clear Thumbnail Cache |
| **Help** | Keyboard Shortcuts, Project Page, Report a Problem, About One Gallery |

**If the global menu stays empty:**
1. Run `./update.sh`. The global menu needs One Gallery on Manjaro's PySide6 (`pyside6`) plus `plasma-integration`, and the script switches older installs over.
2. Make sure a Global Menu widget is in a panel, then **restart One Gallery**. One Gallery checks for the global menu when it starts.
3. Check that `qdbus6 com.canonical.AppMenu.Registrar` (or `qdbus`) lists a service. If it doesn't, the Plasma global-menu service isn't running; adding the widget starts it.

### Keyboard

| Key | Action |
| --- | --- |
| Ctrl + / Ctrl - / Ctrl + wheel | Fewer / more columns |
| Ctrl+F | Search |
| Ctrl+A | Select all |
| Delete | Move selection (or the viewed picture) to the trash |
| Esc | Close viewer / leave selection / go back |
| F5 | Rescan |
| Ctrl+O | Add folder |
| Ctrl+Shift+O | Open picture (without adding its folder) |
| Ctrl+1 / 2 / 3 / 4 / 5 | Pictures / Videos / Albums / Collections / Folders |
| Ctrl+C / Ctrl+Shift+C | Copy picture / copy path |
| Ctrl+P | Print the picture in the viewer |
| Ctrl+Shift+B / Ctrl+Shift+L | Set the picture in the viewer as wallpaper / lock screen |
| Ctrl+Shift+H | Move the selection (or the picture in the viewer) to the private album |
| Ctrl+L / Ctrl+R | Rotate left / right (saved; revert from ⋮) |
| Ctrl+Shift+A | Deselect all |
| Ctrl+Home | Today |
| F11 | Full screen |
| Ctrl+F1 | All keyboard shortcuts |
| Ctrl+Q | Quit |
| Viewer: ← → Space Home End | Navigate |
| Viewer: + − 0, wheel, double-click | Zoom |
| Viewer: F / I / E | Favorite / Details / Edit |
| Viewer, on a video: Enter / double-click, M | Play in the player with sound, mute/unmute the preview |
| Player: Space or K, ← → (5 s), J L (10 s) | Play/pause, seek |
| Player: ↑ ↓ or wheel, M, [ ], 0–9, F | Volume, mute, speed, jump to 0–90 %, full screen |
| Viewer on a video, or player: S | Capture the current frame as a picture |
| Viewer opened from Dolphin: Esc | Close (quits One Gallery) |
| Editor: Ctrl+Z / Ctrl+Shift+Z | Undo / Redo |
| Editor: Ctrl+S / Ctrl+Shift+S | Save / Save as copy |
| Editor: hold \\ | Compare with the original |

## Where data lives

| What | Path |
| --- | --- |
| Settings (watched folders, preferences) | `~/.config/onegallery/config.json` |
| Index (SQLite) | `~/.local/share/onegallery/index.db` |
| Thumbnail cache | `~/.cache/onegallery/thumbs/` (it is safe to delete, and Settings has a **Clear** button) |
| Originals of edited photos | `~/.local/share/onegallery/originals/` (needed for **Revert to original**) |
| Face models (People) | `~/.local/share/onegallery/models/` |
| Town list (Places) | `~/.local/share/onegallery/geo/` |
| Private album (encrypted) | `~/.local/share/onegallery/private/` |
| Photos imported from phones | `~/Pictures/Phone/<phone name>/` (which phones and files were imported: settings file and index) |
| Face thumbnails | `~/.cache/onegallery/faces/` |
| Wallpaper / lock screen copies | `~/.local/share/onegallery/wallpapers/` (the 8 most recent; the wallpaper keeps working if the original moves) |
| Memories widget pictures | `~/.cache/onegallery/widget/` (rebuilt when needed; safe to delete) |

On macOS, everything above is in `~/Library/Application Support/One Gallery/` (the same names, without `onegallery/`), and the caches are in `~/Library/Caches/One Gallery/`.

On Linux, the paths follow `XDG_CONFIG_HOME`, `XDG_DATA_HOME` and `XDG_CACHE_HOME`. Setting `ONEGALLERY_HOME=/some/dir` puts all three under one directory, which is useful for testing. Set `ONEGALLERY_LOG=DEBUG` for verbose logs.

## What is scanned

- Formats: jpg, jpeg, png, webp, gif, bmp, tif, tiff, plus heic/heif when `pillow-heif` is installed, and the video formats listed under [Videos](#videos).
- Skipped: hidden folders, `node_modules`, `.cache`, trash folders, `lost+found`, unreadable or corrupt files, and files smaller than the minimum size (20 KB by default, set in Settings).
- Date taken: EXIF DateTimeOriginal, then DateTimeDigitized or DateTime, then the file's modification time. For videos, the recording date stored in the file, then the modification time.

## Testing and performance

```bash
.venv/bin/python -m unittest discover -s tests -v       # backend tests
.venv/bin/python tools/make_samples.py samples --count 5000
.venv/bin/python tools/ui_smoke.py samples --out ui-shots  # drives the UI, saves screenshots, measures scrolling
.venv/bin/python tools/editor_smoke.py samples --out ui-shots  # editor: tabs, save as copy, save, revert
.venv/bin/python tools/open_with_smoke.py samples --out ui-shots # open a file, browse its folder, hand-off
.venv/bin/python tools/menu_smoke.py samples --out ui-shots     # every menu action in context
.venv/bin/python tools/collections_smoke.py --faces DIR --out ui-shots  # stories, places, people
.venv/bin/python tools/video_smoke.py --out ui-shots      # videos: mixed timeline, Videos tab, preview, player (needs ffmpeg)
.venv/bin/python tools/viewer_menu_smoke.py --out ui-shots # viewer ⋮ menu, Set as, print sheet (prints to PDF)
.venv/bin/python tools/private_smoke.py --out ui-shots     # private album: password, move in / out, lock
.venv/bin/python tools/phone_smoke.py --out ui-shots       # phone sync with a fake KDE Connect phone
.venv/bin/python tools/widget_smoke.py --out ui-shots      # Plasma Memories widget: frame, slide, flip mosaic
.venv/bin/python tools/make_samples.py samples --count 5000 --videos 40   # also add sample videos (needs ffmpeg)
```

With `QT_QPA_PLATFORM=offscreen`, Qt draws with its software renderer, which can't draw video frames. Screenshots then show the poster frame where the video plays. The checks (playing, muted, position, seeking) still run.

`ui_smoke.py` uses a temporary `ONEGALLERY_HOME`, so your real index and settings are not touched.

## Project layout

```
main.py               app entry: Qt setup, image providers, context objects
backend/db.py         SQLite schema; one connection per thread
backend/scanner.py    ScanThread: incremental, mount-aware folder walk + EXIF
backend/video.py      video metadata (ffprobe or the MP4 header) and poster frames (ffmpeg)
backend/desktop.py    set as wallpaper / lock screen (Plasma, with GNOME and macOS fallbacks)
backend/printing.py   printing through CUPS (Qt Print Support) and Save as PDF
backend/vault.py      private album storage: scrypt + AES-256-GCM, chunked file encryption
backend/private.py    private album: move in / out, decrypting image provider, videos
backend/phone.py      phone sync: KDE Connect over D-Bus (busctl), import new photos
backend/widget.py     feed for the Plasma Memories widget (--widget-feed)
backend/watcher.py    watchdog (inotify) live updates
backend/models.py     PhotoModel (rows of thumbnails + day sections), AlbumModel
backend/thumbs.py     async image providers: image://thumbs (disk-cached), image://full
backend/settings.py   folder list + preferences (JSON)
backend/actions.py    trash, open with, show in folder, clipboard
backend/external.py   pictures opened from a file manager (folder browsing without indexing)
backend/collections.py Collections tab: stories, places, people (background jobs)
backend/stories.py    "on this day" memories
backend/geo.py        offline place names (GeoNames)
backend/faces.py      on-device face detection, recognition and grouping (OpenCV)
backend/editor.py     photo editor: edit pipeline, preview provider, save / copy / revert
backend/controller.py glue object exposed to QML as `gallery`
backend/tasks.py      run work on the thread pool, get results on the GUI thread
qml/                  Main.qml, Theme.qml (all colours/sizes), views, components/
packaging/            .desktop file, icon, PKGBUILD, user install script
packaging/plasmoid/   One Gallery Memories, the Plasma 6 desktop / panel widget
packaging/windows/    Windows build: PyInstaller spec, Inno Setup script, build.ps1, icon
packaging/macos/      Mac build: PyInstaller spec, build.sh, icon
tools/                sample generator, UI smoke test
tests/                backend tests
```

## Notes and limitations

- **Share** uses KDE's sharing framework (*Purpose*, package `purpose`, normally installed with Dolphin). Because pip's PySide6 bundles its own Qt, Purpose runs in a small helper under the system Qt (`qml/share/ShareHelper.qml`, started with `/usr/lib/qt6/bin/qml` from `qt6-declarative`). Targets that need input (which KDE Connect device, which e-mail account, …) open a small KDE window. Uploads such as Imgur copy the resulting link to the clipboard. Without Purpose, the menu offers only *Copy to Clipboard*.
- **Edit / Open with** lists the applications that declare support for the file's MIME type, read from their `.desktop` files.
- **Show in folder** asks the file manager over D-Bus (`org.freedesktop.FileManager1`) to open the folder with the file selected. Dolphin supports this. Otherwise the parent folder is opened.
- **Set as** uses `plasma-apply-wallpaperimage` (desktop, every screen) and writes the lock screen picture to `kscreenlockerrc` with `kwriteconfig6`. Both are part of Plasma. The lock screen shows the new picture the next time it locks. On GNOME it uses `gsettings`.
- **Print** lists your CUPS printers (System Settings → Printers). The picture is sent at 300 dpi, with 5 mm margins unless *Borderless* is on, and is turned to landscape automatically when it is wider than tall.
- Video thumbnails come from a frame about one second in (or the first frame of very short clips).
