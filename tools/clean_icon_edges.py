"""Toglie da un'icona gli avanzi delle icone vicine: pezzetti staccati e piccoli che stanno
nella fascia lungo il bordo (le scintille vere, vicine al disegno, restano).

Uso: python tools/clean_icon_edges.py nome1 [nome2 ...] [--band=0.13] [--max=0.02]
     band = fascia del bordo (frazione del lato), max = peso massimo rispetto al pezzo più grande
"""
import sys
from collections import deque
from pathlib import Path

from PIL import Image

ICONS = Path(__file__).resolve().parent.parent / "assets" / "sprites" / "icons"


def clean(path: Path, band: float, max_frac: float) -> int:
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    px = im.load()
    seen = bytearray(w * h)
    parts = []
    for start in range(w * h):
        x, y = start % w, start // w
        if seen[start] or px[x, y][3] <= 8:
            continue
        seen[start] = 1
        q, pix = deque([start]), []
        while q:
            i = q.popleft()
            pix.append(i)
            cx, cy = i % w, i // w
            for j in (i - 1 if cx else -1, i + 1 if cx < w - 1 else -1, i - w, i + w):
                if 0 <= j < w * h and not seen[j] and px[j % w, j // w][3] > 8:
                    seen[j] = 1
                    q.append(j)
        parts.append(pix)
    biggest = max(len(p) for p in parts)
    bx, by = round(w * band), round(h * band)
    removed = 0
    for pix in parts:
        xs = [i % w for i in pix]
        ys = [i // w for i in pix]
        in_band = max(xs) < bx or min(xs) >= w - bx or max(ys) < by or min(ys) >= h - by
        if in_band and len(pix) < biggest * max_frac:
            for i in pix:
                px[i % w, i // w] = (0, 0, 0, 0)
            removed += 1
    im.save(path)
    return removed


if __name__ == "__main__":
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    for name in (a for a in sys.argv[1:] if not a.startswith("--")):
        n = clean(ICONS / f"{name}.png", float(opts.get("band", 0.13)), float(opts.get("max", 0.02)))
        print(name, "pezzi tolti:", n)
