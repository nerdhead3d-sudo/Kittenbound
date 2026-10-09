"""Ritaglia il foglio degli effetti dipinti (PNG trasparente, un effetto per riga) in fotogrammi.

Uso: python tools/slice_vfx.py "<foglio.png>" [--preview=<out.png>]

Righe dall'alto (vedi ROWS): graffio + graffio critico, impatto, parata, parata perfetta, fumo,
polvere, aura del critico, stelline. Output: assets/sprites/vfx/<nome>_<i>.png, tutti i
fotogrammi di un effetto della stessa misura e centrati come nel foglio (l'animazione non balla).
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops

OUT = Path(__file__).resolve().parent.parent / "assets" / "sprites" / "vfx"
ROWS = [                    # (nomi, fotogrammi per nome[, tagli x a mano]) riga per riga
    (["slash", "slash_crit"], 5),
    (["hit"], 6),
    (["parry"], 6),
    (["parry_perfect"], 6, [275, 552, 856, 1105, 1362]),   # passo irregolare: tagli a mano
    (["smoke"], 7),
    (["dust"], 7),
    (["crit_aura"], 7),
    (["stun"], 6),
]
SOLID = 70          # alfa oltre cui un pixel "conta" per trovare righe e fotogrammi


def split(profile, want, regular=True, hint=None):
    """Taglia una proiezione (pixel pieni per riga o colonna) in `want` pezzi, nelle valli:
    fra un effetto e l'altro restano solo poche scintille sparse. `regular` (fotogrammi di
    una riga, a passo fisso): ogni taglio è la valle vicino al punto atteso; altrimenti (le
    righe, alte diverse) le valli più profonde in assoluto.
    Restituisce [(inizio, fine, centro)] con il centro pesato sui pixel pieni."""
    n = len(profile)
    r = 6
    smooth = [sum(profile[max(0, i - r):i + r + 1]) for i in range(n)]
    lo = next(i for i in range(n) if profile[i])            # niente bordi vuoti
    hi = max(i for i in range(n) if profile[i])
    step = (hi - lo) / want
    picks = []
    if hint:                                               # tagli a mano, rifiniti nella valle vicina
        for e in hint:
            picks.append(min(range(e - 12, e + 13), key=lambda i: (smooth[i], abs(i - e))))
    elif regular:
        for j in range(1, want):
            e = lo + step * j
            win = range(max(lo, round(e - step * 0.4)), min(hi, round(e + step * 0.4)))
            picks.append(min(win, key=lambda i: (smooth[i], abs(i - e))))
    else:
        min_gap = round(step / 2)
        for i in sorted(range(lo + min_gap, hi - min_gap), key=lambda i: (smooth[i], i)):
            if len(picks) == want - 1:
                break
            if all(abs(i - j) >= min_gap for j in picks):
                picks.append(i)
    bounds = [0] + sorted(picks) + [n]
    out = []
    for a, b in zip(bounds, bounds[1:]):
        mass = sum(profile[a:b]) or 1
        out.append((a, b, round(sum(i * profile[i] for i in range(a, b)) / mass)))
    return out


def assign(alpha, y0, y1, cells):
    """A quale fotogramma appartiene ogni pixel della riga: di base la colonna, ma ogni pezzo
    staccato (scintilla, spicchio d'anello) va tutto nel fotogramma del suo centro."""
    w = alpha.width
    bh = y1 - y0
    px = alpha.load()
    col_cell = [0] * w
    for k, (a, b, _) in enumerate(cells):
        for x in range(a, b):
            col_cell[x] = k
    owner = [col_cell[i % w] for i in range(w * bh)]
    seen = bytearray(w * bh)
    widest = max(b - a for a, b, _ in cells)
    for start in range(w * bh):
        if seen[start] or px[start % w, y0 + start // w] <= 12:
            continue
        seen[start] = 1
        stack, comp = [start], []
        while stack:
            i = stack.pop()
            comp.append(i)
            x, y = i % w, i // w
            for j in (i - 1 if x else -1, i + 1 if x < w - 1 else -1, i - w, i + w):
                if 0 <= j < w * bh and not seen[j] and px[j % w, y0 + j // w] > 12:
                    seen[j] = 1
                    stack.append(j)
        xs = [i % w for i in comp]
        if max(xs) - min(xs) > widest * 1.3:              # alone che unisce due fotogrammi: resta per colonne
            continue
        k = col_cell[round(sum(xs) / len(xs))]
        for i in comp:
            owner[i] = k
    return owner


def main():
    src = Image.open(sys.argv[1]).convert("RGBA")
    w, h = src.size
    alpha = src.getchannel("A")
    px = alpha.load()
    solid = [[px[x, y] > SOLID for x in range(w)] for y in range(h)]

    rows = split([sum(r) for r in solid], len(ROWS), regular=False)
    OUT.mkdir(parents=True, exist_ok=True)
    sheet_rows = []
    for (names, per, *hint), (y0, y1, _) in zip(ROWS, rows):
        bh = y1 - y0
        prof = [sum(solid[y][x] for y in range(y0, y1)) for x in range(w)]
        # per i tagli: altezza occupata da ogni colonna (un anello vuoto al centro conta pieno)
        span = []
        for x in range(w):
            ys = [y for y in range(y0, y1) if solid[y][x]]
            span.append(ys[-1] - ys[0] + 1 if len(ys) > 1 else len(ys))
        cells = []
        if hint:
            cells = split(span, per, hint=hint[0])
        for g0, g1, _ in ([] if hint else split(span, len(names))):   # più effetti: prima le metà
            cells += [(g0 + a, g0 + b, g0 + c) for a, b, c in split(span[g0:g1], per)]
        cells = [(a, b, round(sum(i * prof[i] for i in range(a, b)) / (sum(prof[a:b]) or 1)))
                 for a, b, _ in cells]                     # centro pesato sui pixel pieni
        owner = assign(alpha, y0, y1, cells)
        band = src.crop((0, y0, w, y1))
        parts = []
        for k, (a, b, cx) in enumerate(cells):
            mask = Image.frombytes("L", (w, bh), bytes(255 if o == k else 0 for o in owner))
            img = band.copy()
            img.putalpha(ImageChops.multiply(band.getchannel("A"), mask))
            bb = img.getchannel("A").point(lambda v: 255 if v > 6 else 0).getbbox() or (a, 0, b, bh)
            parts.append((img, cx, bb))
        # stessa misura per tutti, centrata sul centro del pezzo: l'animazione non balla
        fw = max(2 * max(cx - bb[0], bb[2] - cx) for _, cx, bb in parts) + 4
        for n, name in enumerate(names):
            frames = []
            for img, cx, bb in parts[n * per:(n + 1) * per]:
                frame = Image.new("RGBA", (fw, bh), (0, 0, 0, 0))
                frame.alpha_composite(img.crop((bb[0], 0, bb[2], bh)), (bb[0] - (cx - fw // 2), 0))
                frames.append(frame)
            # taglia il vuoto comune a tutti i fotogrammi (bordo trasparente)
            box = None
            for f in frames:
                bb = f.getchannel("A").point(lambda v: 255 if v > 6 else 0).getbbox()
                if bb:
                    box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]),
                                                  max(box[2], bb[2]), max(box[3], bb[3]))
            for i, f in enumerate(frames):
                f = f.crop(box)
                f.save(OUT / f"{name}_{i}.png")
                frames[i] = f
            sheet_rows.append((name, frames))
            print(f"{name}: {per} fotogrammi {frames[0].size}")

    prev = next((x.split("=", 1)[1] for x in sys.argv[2:] if x.startswith("--preview=")), None)
    if prev:
        cell = 130
        sheet = Image.new("RGBA", (cell * 7 + 160, cell * len(sheet_rows)), (24, 20, 30, 255))
        for r, (name, frames) in enumerate(sheet_rows):
            for i, f in enumerate(frames):
                k = min(1.0, (cell - 10) / max(f.size))
                g = f.resize((max(1, round(f.width * k)), max(1, round(f.height * k))))
                sheet.alpha_composite(g, (160 + i * cell + (cell - g.width) // 2, r * cell + (cell - g.height) // 2))
        sheet.save(prev)


if __name__ == "__main__":
    main()
