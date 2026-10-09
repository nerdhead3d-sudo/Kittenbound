"""Ritaglia il font dipinto (atlante di caratteri su sfondo trasparente) in un glifo per file.

Uso: python tools/slice_font.py "<atlante.png>" [--preview=<out.png>]

Le righe dell'atlante, dall'alto:
    A-Z (2 righe), a-z (2 righe), 0-9 e punteggiatura, simboli
Output: assets/fonts/painted/<codice>.png (codice = ord del carattere) + metrics.json con la
linea di base di ogni glifo, così le minuscole con la gamba (g, p, q, y, j) scendono giuste.
"""
import json
import sys
from collections import deque
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "painted"
ROWS = [
    "ABCDEFGHIJKLM",
    "NOPQRSTUVWXYZ",
    "abcdefghijklm",
    "nopqrstuvwxyz",
    "0123456789!?.,:;'\"-_+=",
    "@#$%&*()[]{}<>/\\|^~`",
]
BASELINE_REF = ["A", "N", "a", "n", "0", None]      # chi dà la linea di base della riga


def components(mask, w, h):
    seen = bytearray(w * h)
    comps = []
    for start in range(w * h):
        if not mask[start] or seen[start]:
            continue
        seen[start] = 1
        q = deque([start])
        x0 = y0 = 10 ** 9
        x1 = y1 = -1
        n = 0
        while q:
            i = q.popleft()
            n += 1
            x, y = i % w, i // w
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            for j in (i - 1 if x else -1, i + 1 if x < w - 1 else -1, i - w, i + w):
                if 0 <= j < w * h and mask[j] and not seen[j]:
                    seen[j] = 1
                    q.append(j)
        if n > 40:
            comps.append([x0, y0, x1, y1])
    return comps


def split_tall(c, mask, w, max_h=170):
    """Due lettere di righe diverse che si toccano (es. la gamba della g sulla t): si
    dividono nel punto più stretto, a metà altezza."""
    x0, y0, x1, y1 = c
    if y1 - y0 <= max_h:
        return [c]
    counts = {y: sum(mask[y * w + x] for x in range(x0, x1 + 1)) for y in range(y0 + 50, y1 - 50)}
    cut = min(counts, key=counts.get)

    def bbox(ya, yb):
        xs = [x for y in range(ya, yb + 1) for x in range(x0, x1 + 1) if mask[y * w + x]]
        ys = [y for y in range(ya, yb + 1) if any(mask[y * w + x] for x in range(x0, x1 + 1))]
        return [min(xs), min(ys), max(xs), max(ys)]
    return [bbox(y0, cut), bbox(cut + 1, y1)]


def main():
    src = Image.open(sys.argv[1]).convert("RGBA")
    w, h = src.size
    alpha = src.getchannel("A").tobytes()
    mask = bytearray(1 if v > 60 else 0 for v in alpha)
    comps = components(mask, w, h)
    comps = [part for c in comps for part in split_tall(c, mask, w)]

    # righe: per centro verticale (le 6 righe hanno altezze diverse ma non si sovrappongono)
    comps.sort(key=lambda c: (c[1] + c[3]) / 2)
    centers = [(c[1] + c[3]) / 2 for c in comps]
    gaps = sorted(range(1, len(comps)), key=lambda i: centers[i] - centers[i - 1])[-(len(ROWS) - 1):]
    rows, start = [], 0
    for cut in sorted(gaps):                       # le righe si separano nei salti più grandi
        rows.append(comps[start:cut])
        start = cut
    rows.append(comps[start:])
    # in ogni riga: i pezzi che si sovrappongono in orizzontale sono lo stesso carattere (i, j, :, ;, ! ...)
    glyph_rows = []
    for row in rows:
        row.sort(key=lambda c: c[0])
        merged = []
        for c in row:
            if merged and c[0] <= merged[-1][2] - 4 or (merged and c[0] - merged[-1][2] < 6
                                                       and abs(c[1] - merged[-1][1]) > 20):
                m = merged[-1]
                m[0], m[1], m[2], m[3] = min(m[0], c[0]), min(m[1], c[1]), max(m[2], c[2]), max(m[3], c[3])
            else:
                merged.append(list(c))
        glyph_rows.append(merged)
    print("glifi per riga:", [len(r) for r in glyph_rows], "attesi:", [len(r) for r in ROWS])
    if [len(r) for r in glyph_rows] != [len(r) for r in ROWS]:
        sys.exit("Il numero di caratteri non torna: controlla l'atlante.")

    OUT.mkdir(parents=True, exist_ok=True)
    metrics = {}
    cap = None
    for chars, boxes, ref in zip(ROWS, glyph_rows, BASELINE_REF):
        if ref is not None:
            base = boxes[chars.index(ref)][3]
        else:                                           # simboli: la linea di base della riga
            base = sorted(b[3] for b in boxes)[len(boxes) // 2]
        if ref == "A":
            cap = boxes[0][3] - boxes[0][1]
        for ch, (x0, y0, x1, y1) in zip(chars, boxes):
            img = src.crop((x0 - 2, y0 - 2, x1 + 3, y1 + 3))
            img.save(OUT / f"{ord(ch)}.png")
            metrics[ch] = {"w": img.width, "h": img.height, "base": base - (y0 - 2)}
    json.dump({"cap": cap, "glyphs": metrics}, open(OUT / "metrics.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    print(f"{len(metrics)} glifi in {OUT} (altezza maiuscole {cap}px)")

    prev = next((a.split("=", 1)[1] for a in sys.argv[2:] if a.startswith("--preview=")), None)
    if prev:
        sheet = Image.new("RGBA", (1400, 120 * len(ROWS)), (30, 26, 40, 255))
        for r, chars in enumerate(ROWS):
            x = 10
            for ch in chars:
                g = Image.open(OUT / f"{ord(ch)}.png")
                k = 60 / cap
                g = g.resize((max(1, round(g.width * k)), max(1, round(g.height * k))))
                m = metrics[ch]
                sheet.alpha_composite(g, (x, r * 120 + 90 - round(m["base"] * k)))
                x += g.width + 2
        sheet.save(prev)


if __name__ == "__main__":
    main()
