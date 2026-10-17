"""Measure RapidOCR read time at different intra-op thread counts on this machine, on synthetic
HUD-sized regions, so the booth's screen.ocr_threads can be set from data."""
import statistics
import time

import numpy as np


def bench(engine, img, n=7):
    arr = np.array(img)
    engine(arr)  # warm up (first call loads the models / JITs)
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        engine(arr)
        ts.append(time.perf_counter() - t)
    return statistics.median(ts), min(ts)


def _synthetic():
    """HUD-like region crops (screen grab can't run over SSH). Sizes match the lie/slope/others
    boxes at 4K; the thread-scaling is what we're measuring, not exact pixels."""
    from PIL import Image, ImageDraw

    specs = [((300, 110), ["Rough"]), ((300, 130), ["4.7° UP", "3.3° LEFT"]),
             ((340, 240), ["Wes", "150.2 YDS", "E", "Toby", "126.4 YDS"])]
    imgs = []
    for (w, h), lines in specs:
        im = Image.new("RGB", (w, h), (15, 20, 30))
        d = ImageDraw.Draw(im)
        for i, t in enumerate(lines):
            d.text((10, 8 + i * 42), t, fill=(235, 235, 235))
        imgs.append(im)
    return imgs


def main():
    regions = _synthetic()
    from rapidocr import RapidOCR
    for threads in (4, 8, 12, 16):
        eng = RapidOCR(params={"EngineConfig.onnxruntime.intra_op_num_threads": threads})
        per = [bench(eng, r) for r in regions]
        total_med = sum(p[0] for p in per)
        print(f"threads={threads:2d}  per-region medians {[round(p[0],3) for p in per]}  "
              f"sum(3 regions)={total_med:.3f}s")


if __name__ == "__main__":
    main()
