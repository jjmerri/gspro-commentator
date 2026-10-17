"""Grab a full-screen screenshot for calibrating OCR regions on a non-HUD screen (GSPro's setup and
course-load screens). Standalone: needs only mss + Pillow, no booth config.

Run on the sim PC, then bring the screen you want to the front during the countdown:

    .venv\\Scripts\\python.exe tools\\capture_screen.py setup --delay 8
    .venv\\Scripts\\python.exe tools\\capture_screen.py load  --delay 8

Each run writes <name>.png (a 100px grid overlay, for reading pixel coords) and <name>_raw.png
(clean) under logs/. Monitor defaults to 1 (the booth's screen.monitor); pass --monitor to change it.
"""
import argparse
import time
from pathlib import Path

import mss
from PIL import Image, ImageDraw


def grab(monitor: int) -> Image.Image:
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[monitor])
    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def with_grid(img: Image.Image) -> Image.Image:
    out = img.copy()
    draw = ImageDraw.Draw(out)
    for x in range(0, out.width, 100):
        draw.line([(x, 0), (x, out.height)], fill=(255, 0, 255), width=1)
        draw.text((x + 2, 2), str(x), fill=(255, 255, 0))
    for y in range(0, out.height, 100):
        draw.line([(0, y), (out.width, y)], fill=(255, 0, 255), width=1)
        draw.text((2, y + 2), str(y), fill=(255, 255, 0))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name", nargs="?", default="screen", help="Output name stem (e.g. 'setup', 'load')")
    ap.add_argument("--delay", type=int, default=8, help="Countdown seconds before grabbing")
    ap.add_argument("--monitor", type=int, default=1, help="mss monitor index (booth uses 1)")
    ap.add_argument("--out-dir", default="logs", help="Where to write the PNGs")
    args = ap.parse_args()

    for n in range(args.delay, 0, -1):
        print(f"Grabbing {args.name!r} in {n}s... bring that screen to the front", end="\r", flush=True)
        time.sleep(1)
    print(" " * 70, end="\r")

    img = grab(args.monitor)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / f"{args.name}_raw.png"
    grid = out_dir / f"{args.name}.png"
    img.save(raw)
    with_grid(img).save(grid)
    print(f"Saved {grid} ({img.width}x{img.height}, 100px grid) and {raw} (clean).")


if __name__ == "__main__":
    main()
