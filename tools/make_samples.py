#!/usr/bin/env python3
"""Generate a folder of sample photos for testing One Gallery's scroll performance.

    python tools/make_samples.py ~/Pictures/onegallery-samples --count 5000 [--videos 40]

Images get random EXIF DateTimeOriginal values over the last few years (some get
none, so the mtime fallback is exercised), a mix of orientations and formats, and
a few deliberately broken or tiny files that the scanner must skip gracefully.
"""

import argparse
import os
import random
import shutil
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont

FOLDERS = ["Camera", "Camera", "Camera", "Screenshots", "WhatsApp Images",
           "Trips/Lisbon 2024", "Trips/Alps", "Downloads", "Pets"]


def _palette(rng):
    hue = rng.random()
    import colorsys
    a = colorsys.hsv_to_rgb(hue, 0.55, 0.95)
    b = colorsys.hsv_to_rgb((hue + 0.15) % 1, 0.7, 0.55)
    return tuple(int(c * 255) for c in a), tuple(int(c * 255) for c in b)


def make_one(args):
    out_dir, index, seed, years = args
    rng = random.Random(seed)
    folder = rng.choice(FOLDERS)
    when = datetime.now() - timedelta(days=rng.random() * 365 * years,
                                      seconds=rng.randint(0, 86400))
    portrait = rng.random() < 0.3
    w, h = (360, 480) if portrait else (480, 360)
    if folder == "Screenshots":
        w, h = 360, 760
    c1, c2 = _palette(rng)
    gradient = Image.linear_gradient("L").resize((w, h))
    img = Image.composite(Image.new("RGB", (w, h), c1), Image.new("RGB", (w, h), c2), gradient)
    noise = Image.effect_noise((w, h), 40).convert("RGB")
    img = Image.blend(img, noise, 0.18)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=36)
    except TypeError:
        font = ImageFont.load_default()
    draw.text((20, 20), when.strftime("%Y-%m-%d"), fill="white", font=font)
    draw.text((20, 64), f"#{index}", fill="white", font=font)

    target = os.path.join(out_dir, folder)
    os.makedirs(target, exist_ok=True)
    stamp = when.strftime("%Y%m%d_%H%M%S")
    if folder == "Screenshots":
        path = os.path.join(target, f"Screenshot_{stamp}_{index}.png")
        img.save(path, "PNG")
    else:
        path = os.path.join(target, f"IMG_{stamp}_{index}.jpg")
        exif = Image.Exif()
        if rng.random() < 0.9:  # 10 % without EXIF date -> mtime fallback
            exif_ifd = exif.get_ifd(0x8769)
            exif_ifd[36867] = when.strftime("%Y:%m:%d %H:%M:%S")
        img.save(path, "JPEG", quality=88, exif=exif)
    ts = time.mktime(when.timetuple())
    os.utime(path, (ts, ts))
    return path


def make_broken(out_dir):
    junk = os.path.join(out_dir, "Downloads")
    os.makedirs(junk, exist_ok=True)
    with open(os.path.join(junk, "corrupt.jpg"), "wb") as f:
        f.write(b"\xff\xd8\xff\xe0" + os.urandom(30_000))  # JPEG magic, garbage body
    with open(os.path.join(junk, "not_an_image.png"), "wb") as f:
        f.write(b"hello" * 6000)
    Image.new("RGB", (16, 16), "red").save(os.path.join(junk, "tiny_icon.png"))  # < 20 KB
    hidden = os.path.join(out_dir, ".hidden")
    os.makedirs(hidden, exist_ok=True)
    Image.new("RGB", (600, 600), "blue").save(os.path.join(hidden, "secret.bmp"))


def make_video(args):
    """A short clip with a recording date (needs ffmpeg)."""
    out_dir, index, seed, years = args
    rng = random.Random(seed)
    folder = os.path.join(out_dir, rng.choice(["Camera", "Camera", "WhatsApp Video", "Trips/Alps"]))
    os.makedirs(folder, exist_ok=True)
    when = datetime.now() - timedelta(days=rng.random() * 365 * years, seconds=rng.randint(0, 86400))
    portrait = rng.random() < 0.4
    size = "360x640" if portrait else "640x360"
    seconds = rng.choice([3, 5, 8, 12])
    path = os.path.join(folder, f"VID_{when:%Y%m%d_%H%M%S}_{index}.mp4")
    utc = datetime.fromtimestamp(when.timestamp(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25",
                    "-f", "lavfi", "-i", f"sine=frequency={rng.randint(220, 880)}", "-t", str(seconds),
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-metadata", f"creation_time={utc}", path], check=True)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir")
    parser.add_argument("--count", type=int, default=5000)
    parser.add_argument("--years", type=float, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--videos", type=int, default=0, help="also write this many short videos (needs ffmpeg)")
    args = parser.parse_args()

    out_dir = os.path.abspath(os.path.expanduser(args.out_dir))
    os.makedirs(out_dir, exist_ok=True)
    start = time.time()
    jobs = [(out_dir, i, args.seed * 1_000_003 + i, args.years) for i in range(args.count)]
    with ProcessPoolExecutor() as pool:
        for n, _ in enumerate(pool.map(make_one, jobs, chunksize=64), 1):
            if n % 500 == 0:
                print(f"{n}/{args.count}")
    make_broken(out_dir)
    print(f"Wrote {args.count} images to {out_dir} in {time.time() - start:.1f}s")
    if args.videos > 0:
        if not shutil.which("ffmpeg"):
            print("ffmpeg not found: no videos written (sudo pacman -S ffmpeg)")
            return
        jobs = [(out_dir, i, args.seed * 7_000_003 + i, args.years) for i in range(args.videos)]
        with ProcessPoolExecutor(max_workers=4) as pool:
            list(pool.map(make_video, jobs))
        print(f"Wrote {args.videos} videos")


if __name__ == "__main__":
    main()
