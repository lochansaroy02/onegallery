# One Gallery: feature ideas

Ideas that would set One Gallery apart from other Linux galleries (Gwenview, digiKam, Shotwell, Koko), chosen to fit what already exists. Every idea keeps the app's core promise: **on-device, no cloud, no account**.

Each idea lists:
- **Why it stands out:** what makes it different.
- **How:** how it fits the current code and dependencies. Anything new stays an *optional* extra, the way `opencv` is for People.
- **Effort:** S = a few days, M = about a week or two, L = several weeks.

This list leaves out what One Gallery already has: videos, the private album, Stories, Places, People, the editor, printing, Set as wallpaper, the KDE share menu, phone sync, themes, live updates, and use as the default viewer.

---

## 1. Signature features (the headline ideas)

### 1.1 Samsung / Google Motion Photos
Samsung and Pixel phones save "motion photos": a short MP4 clip stored inside the JPEG. Almost no desktop gallery plays them, and phone sync already brings these files in.
- **Why it stands out:** this is the feature that best fits a One UI-style app. It shows a "Motion" badge on the thumbnail, plays the clip when you hover over or open the picture, and lets you **Export clip** or **Save a still frame**.
- **How:**
  - At scan time, find the embedded clip: the `MotionPhoto` / `MicroVideoOffset` XMP tags, or the `MotionPhoto_Data` marker Samsung uses.
  - Add a `motion_offset` column to the index.
  - Write the clip to `~/.cache/onegallery/motion/` the first time it's needed.
  - Play it with the existing `VideoSurface.qml`.
- **Effort:** M

### 1.2 Natural-language search ("dog on the beach", "receipt", "sunset 2023")
On-device semantic search with a small CLIP-style image/text model.
- **Why it stands out:** Linux galleries only search by name, tag or date. This brings Google Photos-style search to the desktop, fully offline.
- **How:**
  - Run a quantised ONNX CLIP model (about 90 MB, downloaded on first use the way the face models are) through the OpenCV DNN that `faces.py` already uses. Fall back to `onnxruntime` if needed.
  - Compute embeddings in a background task and store them as BLOBs in a new `embeddings` table.
  - Search with a brute-force cosine scan over NumPy. 50k images × 512 floats is about 100 MB, which takes milliseconds.
  - Combine the results with the current name/folder/date search in `SearchPage.qml`.
- **Effort:** L

### 1.3 Text in pictures (OCR)
Search screenshots and photos by the words in them, and use **Copy text** in the viewer (One UI's "Extract text").
- **Why it stands out:** screenshots are often the bulk of a desktop library, and finding "that screenshot with the error message" becomes instant.
- **How:**
  - Use the system `tesseract` when it's installed (optional, like `ffmpeg`).
  - OCR only screenshots and pictures with a lot of text: detect those with a cheap edge-density check.
  - Store the text in an FTS5 table that search can query.
  - Draw selectable text boxes over the picture in `ViewerPage.qml`.
- **Effort:** M

### 1.4 Clean-up assistant (duplicates, near-duplicates, blurry shots)
A "Free up space" page in Collections:
- exact duplicates
- near-duplicates and bursts, with the best shot chosen for you
- blurry or very dark shots
- old screenshots
- very large videos
- **Why it stands out:** desktop libraries pile up copies from phone backups, WhatsApp exports and old drives. Showing "Save 14 GB" with one-tap review is something people talk about.
- **How:**
  - A perceptual hash (dHash with Pillow, no new dependency) stored in the index, then Hamming-distance grouping.
  - Blur score from the variance of the Laplacian (OpenCV if present, otherwise a Pillow filter).
  - The "best shot" ranking reuses the burst logic Stories already has.
  - Deleting goes through the existing trash code.
- **Effort:** M

### 1.5 Recently deleted (30-day in-app trash)
One UI keeps deleted items in the Gallery for 30 days, with **Restore** and **Delete forever**.
- **Why it stands out:** a safety net that also covers deletes made from the clean-up assistant and the editor.
- **How:**
  - Keep sending files to the system trash.
  - Record them in a `deleted` table: original path, trash path, date.
  - Add a "Recently deleted" album that reads that table.
  - Restore moves the file back using the freedesktop `.trashinfo` file (or the Windows/macOS equivalents in `desktop.py` / `macos.py`).
  - Purge entries older than 30 days on startup.
- **Effort:** S–M

---

## 2. One UI-inspired extras

| Idea | What it does | How | Effort |
|---|---|---|---|
| **Object eraser** | Brush over an unwanted object or person and remove it. | Use OpenCV `inpaint` (Telea) for small areas. Optionally use a LaMa ONNX model for large ones. Add it as a new tool in `EditorPage.qml`. | M–L |
| **Lift subject / remove background** | Long-press the subject to copy it as a transparent PNG sticker, or save it. | Run a U²-Net / BiRefNet ONNX model through OpenCV DNN, then put the result on the clipboard as a PNG with transparency. | M |
| **Remaster** | One-click auto-enhance plus 2×/4× upscaling for old photos. | Auto-levels and denoise in `editor.py`. Optional upscaling through system `realesrgan-ncnn-vulkan` when it's installed. | M |
| **Create ▸ GIF / Collage / Highlight video** | Turn a selection into a GIF, a collage (2–9 photo layouts) or a short video with music. | Build GIFs and collages with Pillow. Build videos with ffmpeg and the transitions `StoryPlayer` already uses. Add it to `SelectionBar.qml`. | M |
| **Story export** | Save any Story as an MP4 to share. | Render the `StoryPlayer` timeline with ffmpeg. | S–M |
| **Portrait-style background blur** | Add or adjust background blur after the photo was taken. | A depth model (MiDaS-small ONNX) plus a graded blur. | L |
| **Bixby-style "Suggestions" card** | The top of Pictures suggests things like "3 blurry photos to delete", "New story from 2022" or "12 photos from your phone". | Collect the clean-up assistant, Stories and phone sync results into one dismissible card. | S |

---

## 3. Deep KDE Plasma integration (what makes it *the* KDE gallery)

| Idea | What it does | How | Effort |
|---|---|---|---|
| **KRunner plugin** | Type "photos beach" in KRunner to see thumbnails and open the picture in One Gallery. | A D-Bus KRunner plugin (`org.kde.krunner1`) answered from the index, plus a `.desktop` registration file in `packaging/`. | S–M |
| **Plasma widget: Memories frame** | A desktop or panel widget that cycles through today's Stories or favorites. | A Plasmoid (QML) reading a small JSON feed that One Gallery writes, so it needs no Python. | M |
| **Wallpaper plugin / daily wallpaper** | Rotate the wallpaper through favorites, a chosen album, or "On this day". | Reuse the existing *Set as wallpaper* code on a timer, or ship a Plasma wallpaper plugin. | S |
| **Dolphin service menu** | Right-click in Dolphin: *Add to One Gallery*, *Open in One Gallery*, *Add to private album*. | A `.desktop` service menu that calls `onegallery --add/--open` (needs CLI flags in `main.py`). | S |
| **Baloo tags and ratings** | Show the tags and star ratings set in Dolphin, and write them back. | Read and write the `user.xdg.tags` / `user.baloo.rating` extended attributes with `os.getxattr`, so no new dependency. | S–M |
| **Plasma notifications with actions** | "42 photos imported from Pixel 8 — View". | Freedesktop notifications through D-Bus (`QDBus`), so the toast also works when the window is closed. | S |
| **Spectacle integration** | New screenshots appear at once in a "Screenshots" album, with OCR already done. | Watch Spectacle's save folder automatically, then run OCR (1.3) on the new files. | S |

---

## 4. Power-user and photographer features

| Idea | What it does | How | Effort |
|---|---|---|---|
| **RAW support** | Show CR2/NEF/ARW/DNG files. A RAW+JPEG pair is shown as one item. | Use the embedded JPEG preview for thumbnails and the viewer (fast, no decoding). Use `rawpy` (optional) for full quality. | M |
| **Culling mode** | Lightroom-style keyboard flow: P to pick, X to reject, 1–5 to rate, then a preloaded next picture. | A viewer mode with a `rating`/`flag` column. Batch-delete the rejects. | M |
| **XMP sidecars / digiKam compatibility** | Ratings, tags and edits go into `.xmp` files that other apps can read. | Read and write simple XMP RDF with the standard library (`xml.etree`). | M |
| **Fix dates / time shift** | Batch-correct a wrong camera clock ("+3 h for this trip") or set a date on scanned photos. | Write EXIF with Pillow, then update `taken` in the index. | S–M |
| **Geotag from GPX / map pick** | Add a location to photos that have none, from a GPX track or by picking a spot on the map. | Match photos to the GPX track by time, write GPS EXIF, then refresh Places. | M |
| **Interactive map view** | Places as a zoomable map with photo clusters, not just a list of towns. | QtLocation with OpenStreetMap tiles (cached) in `PlacesPage.qml`. | M |
| **Non-destructive edit history** | Every edit can be undone at any later time, not just in the current session. | Store the edit stack as JSON next to the saved original that `editor.py` already keeps, and re-render on demand. | M |
| **Side-by-side compare** | Compare 2–4 selected photos with zoom and pan linked. | A split view in `ViewerPage.qml`. | S–M |
| **Smart albums (rules)** | For example "Screenshots containing 'invoice'", "Videos > 1 min from 2024", or "Favorites in Goa". | Save searches as rules and run them as SQL with FTS. | M |
| **Storage insights** | Space used per folder, year, type and phone, with charts. | Aggregate queries in the existing index. Add a page under Settings. | S |

---

## 5. Privacy-first features (lean into "no cloud")

| Idea | What it does | How | Effort |
|---|---|---|---|
| **Remove location when sharing** | A share-menu toggle that strips GPS and other metadata before files leave the machine (One UI has this). | Re-save a temporary copy without EXIF in `share.py` before handing it over. | S |
| **Privacy scanner** | Flags photos that show IDs, cards, QR codes, documents or screenshots of chats, and offers to move them to the private album. | OCR keywords plus the OpenCV QR detector. Moving uses the existing `private.py`. | M |
| **LAN share link** | Share an album with family on the same Wi-Fi: One Gallery shows a QR code, and phones open a temporary web page to view or download. | A small standard-library `http.server` on a random port with a one-time token and an expiry. Only on when the user turns it on. | M |
| **Encrypted backup** | Back up the library and index to an external drive or NAS, incremental and optionally encrypted. | Reuse the `cryptography` code from `vault.py` and the mtime/size change detection the scanner already has. | M–L |
| **Self-hosted bridge** | Optional two-way sync with Immich or Nextcloud Photos for people who already run them. | Their REST and WebDAV APIs, opt-in only. | L |

---

## 6. Small touches that feel premium

- **Hover scrub:** move the mouse across a video thumbnail to scrub through it (frames from the existing ffmpeg thumbnailer). **S**
- **Animated GIF/WebP thumbnails** that play on hover. **S**
- **"On this day" notification** each morning when a Story exists. **S**
- **Drag out:** drag thumbnails straight into Telegram, a browser or Dolphin (Qt drag with file URLs). **S**
- **Quick look:** hold Space over a thumbnail for a big preview; let go to close. **S**
- **Colour search:** "blue", "red car" (dominant-colour histogram stored at scan time). **S–M**
- **Accessible descriptions:** auto-generated alt text read by screen readers (from the same model as 1.2). **M**
- **Pinch-zoom timeline:** Day → Month → Year with the same animated grid morph One UI uses. Build on the existing day/month/year view. **S–M**

---

## Suggested order

1. **Quick wins** (S, no new dependencies):
   - Recently deleted
   - Remove location when sharing
   - Dolphin service menu
   - Baloo tags and ratings
   - Hover scrub
   - Drag out
2. **Signature release:**
   - Motion Photos
   - Clean-up assistant
   - OCR text search

   These three make the clearest "only One Gallery does this" pitch.
3. **AI release:**
   - natural-language search
   - Object eraser
   - Lift subject
   - Remaster

   All are optional downloads, the same way the People models are.
4. **Ecosystem release:**
   - KRunner plugin
   - Plasma Memories widget
   - LAN share link
   - Encrypted backup
