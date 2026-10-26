# Build the One Gallery landing page

Build a marketing landing page for **One Gallery**, the desktop photo and video gallery in this repository. The page should make a KDE / Linux user (and a Windows user) want to install it within a minute of landing, and it should show the real app, not mock-ups.

Read `README.md` first. It is the source of truth for features, install steps and platform details. Where this prompt and the README disagree, the README wins. Tell me about the mismatch.

## What One Gallery is (the pitch)

A phone-style gallery for the desktop, styled after Samsung One UI's Gallery app. You pick the folders it shows, including folders on other drives. It indexes them in the background and lists your pictures and videos newest first, grouped by day, like the gallery on your phone.

- Runs on Arch-based Linux (Manjaro) with KDE Plasma, on Wayland and X11. Also runs on Windows 10 (1809 or newer) and 11, 64-bit.
- Free and open source, MIT licence. Current version: read `version` in `pyproject.toml` (0.3.0 at the time of writing).
- Everything stays on your machine: the index, thumbnails, face grouping and the encrypted private album. There is no account and no cloud.

Suggested hero line (improve it if you can): **"Your phone's gallery, on your desktop."** Sub-line: one sentence on "the folders you choose, newest first, grouped by day, made for KDE Plasma."

## Who the page is for

1. KDE Plasma users on Arch / Manjaro who are tired of file-manager browsing and want a phone-like photo timeline.
2. Samsung / Android users who like One UI or Material You and want the same feel on their PC.
3. Windows users who want a fast, local, no-account gallery.

Write for people, not developers. Keep the tech stack (Python, PySide6, QML, SQLite) to one small "Built with" line near the footer.

## Sections

Use roughly this order. Merge or reorder sections if the page reads better.

1. **Hero:** headline, sub-line, two buttons (**Install on Linux**, **Download for Windows**), a secondary **View on GitHub** link, and a large screenshot of the Pictures tab.
2. **Feature highlights** (the big three, each with its own screenshot):
   - **Timeline like your phone:** day headers that stay visible ("Today", "Yesterday", "Fri, Oct 23"), a title that shrinks as you scroll, a fast-scroll handle with a month bubble, and Ctrl + wheel to change the number of columns. Smooth with 50,000+ pictures.
   - **Make it yours:** Black & white or **Material You** colour style, light / dark following KDE, KDE's accent colour (it updates live), and a **Liquid Glass** navigation bar (Frosted or Clear) that bends the photos behind it like thick glass.
   - **Private album:** password-protected and encrypted. Pictures moved into it disappear from their folders and from the rest of One Gallery.
3. **Feature grid** (short cards, icon + title + one line each):
   - Videos: in the timeline with a length badge, plus a Videos tab and a built-in player.
   - Albums: one per folder or sub-folder, plus Favorites.
   - Collections: **Stories** (this day in earlier years), **Places** (from GPS), **People** (on-device face grouping).
   - Photo editor: crop, rotate, straighten, 9 filters, 10 adjustments, undo/redo, hold to compare, save as copy, revert to original.
   - Viewer: swipe, zoom, pan, Details panel, Set as wallpaper / lock screen, Print or Save as PDF.
   - Selection mode: select a whole day, then delete to trash, share, open with, copy path, show in folder.
   - KDE Share menu: KDE Connect, Bluetooth, e-mail, Telegram, Nextcloud and the rest of Dolphin's Share menu.
   - Search: by name, folder or date (`2025`, `October`, `oct 2024`).
   - Live updates, and drives that are unplugged are kept and marked *unavailable* rather than removed.
   - Default image viewer: open pictures from Dolphin or Explorer in One Gallery.
   - KDE global menu, native file dialogs, keyboard shortcuts.
   - Safe by design: removing a folder never deletes files, and delete goes to the trash / Recycle Bin.
4. **Screenshot gallery:** a light/dark toggle or a carousel showing the remaining screenshots (see the list below). Clicking one opens it full size.
5. **Install:** tabs for each install method, with copyable commands taken from the README:
   - **AUR (recommended):** `yay -S onegallery` (or `paru -S onegallery`); `onegallery-git` for the newest commit; the manual `makepkg -si` route; the optional extras line (`python-pillow-heif python-opencv python-watchdog purpose`).
   - **From source:** `git clone https://github.com/lochansaroy02/onegallery.git`, `cd onegallery`, `./update.sh --install`.
   - **Windows:** download `OneGallery-<version>-setup.exe` from Releases. Say plainly that the installer is not code-signed yet, so SmartScreen may warn the first time (**More info → Run anyway**).
6. **FAQ** (short): Does it change or move my files? (No, except the private album, which moves files in on purpose.) Where is my data kept? (Paths from the README.) Does it work on GNOME? (It runs anywhere PySide6 does, but KDE-only parts such as the global menu and Share menu need Plasma. Check the README before claiming more.) Is it free? (Yes, MIT.)
7. **Footer:** GitHub, Releases, AUR, Issues, Licence, "Built with Python, Qt Quick (PySide6) and SQLite", copyright from `LICENSE`.

## Links

| Purpose | URL |
| --- | --- |
| Source code | https://github.com/lochansaroy02/onegallery |
| Releases (Windows installer) | https://github.com/lochansaroy02/onegallery/releases |
| Latest release | https://github.com/lochansaroy02/onegallery/releases/latest |
| Issues / feedback | https://github.com/lochansaroy02/onegallery/issues |
| AUR package | https://aur.archlinux.org/packages/onegallery |
| AUR git package | https://aur.archlinux.org/packages/onegallery-git |
| Licence | https://github.com/lochansaroy02/onegallery/blob/main/LICENSE |

Before using a link, check that it works (for example with `curl -sI`). If one doesn't, leave it out and tell me; don't guess a replacement.

## Files to reference or reuse

- `packaging/icon.svg`: the app icon. Use it as the logo and favicon. Don't redraw it.
- `packaging/windows/onegallery.ico`: Windows icon (not needed on the web, but it shows the icon at small sizes).
- `packaging/onegallery.desktop`, `packaging/PKGBUILD`, `packaging/aur/`: the Linux packaging, for accurate install details.
- `packaging/windows/build.ps1`, `.github/workflows/windows.yml`: how the Windows installer is built and released.
- `qml/Theme.qml`: the app's colours, corner radii, spacing and fonts. Take the landing page's palette and radii from here, so the site looks like the app.
- `qml/shaders/liquidglass.frag`: the Liquid Glass effect. Recreate the look on the page with CSS (`backdrop-filter`, a highlight along the top edge); don't port the shader.
- `README.md`: feature details, install commands, data locations, keyboard shortcuts.

## Screenshots

No screenshots are committed. Generate them from the real app with the UI test scripts in `tools/`. They drive the app offscreen with a throw-away `ONEGALLERY_HOME`, so my real library is never touched.

```bash
.venv/bin/python tools/make_samples.py samples --count 300
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/ui_smoke.py samples --out site/raw-shots
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/video_smoke.py --out site/raw-shots
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/collections_smoke.py --out site/raw-shots
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/editor_smoke.py samples --out site/raw-shots
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/viewer_menu_smoke.py --out site/raw-shots
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/private_smoke.py --out site/raw-shots
```

Check each script's arguments (`--help`) before running it; the lines above may be out of date.

**Important:** `make_samples.py` makes synthetic coloured placeholder images. They are fine for checking layout but look bad on a marketing page. Before taking the final screenshots, ask me for a folder of real photos I'm happy to publish (or a source of freely licensed photos I approve). If I don't give one, use the placeholders and list every screenshot that needs replacing in your final message.

Screenshots the page needs (file names from the scripts in brackets):

- Pictures tab, light (`02-pictures`) and dark (`13-dark-pictures`): hero and timeline section
- Collapsed header while scrolling (`04-collapsed-header`)
- Eight columns (`05-eight-columns`)
- Selection mode (`06-selection`)
- Viewer and Details panel (`07-viewer`, `08-viewer-details`, `15-dark-viewer`)
- Albums (`09-albums`) and Search (`11-search`)
- Settings, now a tab in the navigation bar (`12-settings`)
- Videos tab and player (`v2-videos-tab`, `v4-player-paused`)
- Collections: Stories, Places, People (`c2-collections-ready`, `c5-places-page`, `c6-story-playing`)
- Photo editor (`e01-transform` and an Adjust / Filters shot)
- Viewer menu, Set as, Print sheet (`m1-viewer-menu-light`, `m2-set-as`, `m4-print-sheet`)
- Private album (`p4-private-grid`, `p7-unlock-dark`)
- **Not covered by the scripts yet; write a small script for these the same way:**
  - Liquid Glass nav bar, Frosted and Clear, over a colourful part of the grid (`prefs.navStyle = 'frosted' | 'clear'`)
  - Material You with two or three different accents (`prefs.colorStyle = 'tinted'`, `prefs.accent = '#…'`)

For the final images, use a 1440×900 window, crop out empty areas, export WebP (with a PNG fallback only if needed), keep each under ~300 KB, and give each one a descriptive `alt` text. Put them in `site/assets/screenshots/`. Leave `site/raw-shots/` out of git (add it to `.gitignore`).

## Design direction

- The page should feel like the app: One UI's soft, rounded, spacious style. Corner radii 16–28 px, generous padding, no hard borders, large bold headings, regular-weight body text. Take the exact values from `qml/Theme.qml` (One UI blue accent `#3E91FF`, light background ~`#F6F6F6`, dark ~`#000` with surfaces ~`#1C1C1E`).
- Light and dark themes following `prefers-color-scheme`, plus a manual toggle. Show the dark screenshots in dark mode.
- Show screenshots in a simple window frame with soft shadows, not inside a fake laptop.
- A floating pill navigation bar at the bottom on phones, like the app's own bar, with a Liquid Glass (`backdrop-filter`) look. Use a normal top bar on desktop.
- Motion: subtle (150–300 ms) fade/slide-in as sections enter the screen, and nothing at all when `prefers-reduced-motion` is set.
- System font stack (Noto Sans / Open Sans / Segoe UI / system-ui). No web fonts unless they clearly add something.

## Technical requirements

- Put it in `site/` in this repository: `site/index.html`, `site/styles.css`, `site/main.js`, `site/assets/`. Plain HTML, CSS and a little JavaScript. No framework and no build step, so GitHub Pages can serve it directly.
- Optionally add `.github/workflows/pages.yml` that publishes `site/` to GitHub Pages. Ask me before enabling Pages or pushing anything.
- Responsive from 360 px to 1920 px wide, with no horizontal scrolling.
- Accessible: semantic landmarks, one `h1`, alt text on every image, visible focus styles, WCAG AA contrast in both themes, everything reachable by keyboard (tabs, carousel, lightbox, copy buttons).
- Copy buttons on every install command, with a "Copied" confirmation.
- Fast: lazy-load images below the fold, set `width`/`height` on every image, and aim for a Lighthouse score of 90+ in every category.
- SEO and sharing: `<title>`, meta description, Open Graph and Twitter card tags (use a 1200×630 image made from the hero screenshot), favicon from `packaging/icon.svg`, and `SoftwareApplication` JSON-LD (name, operating systems, licence, free price, download URL).
- No trackers, no analytics, no cookie banner, and no external requests except links the user clicks.

## Honesty rules

- Only claim what the app does today. Check every feature on the page against `README.md` or the code.
- No made-up download counts, star counts, ratings, testimonials or press quotes. If you want social proof, add a live "Star on GitHub" link and nothing else.
- Don't call the Windows installer signed or verified. Don't say it works on macOS.
- Make KDE-only features clear (global menu, KDE Share menu, Set as lock screen on Plasma).

## How to work

1. First show me a short plan: the section outline, the screenshot list, and a sketch of the design direction. Wait for my OK.
2. Generate the screenshots, then build the page.
3. Open it in a browser at 390 px, 768 px and 1440 px wide, in light and dark mode, and fix anything that looks wrong. Run Lighthouse (or explain why you couldn't).
4. At the end, tell me how to preview it locally (for example `python -m http.server -d site`), list any links you couldn't check, and list any placeholder screenshots still on the page.
