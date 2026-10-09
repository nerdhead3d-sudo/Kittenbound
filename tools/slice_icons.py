"""Ritaglia le icone di oggetti e magie dal foglio generato (sfondo trasparente).

Uso: python tools/slice_icons.py <foglio.png> [nomi...]   (senza nomi: tutte)
Ogni pezzo (zona collegata) va tutto all'icona più vicina, anche se esce dal riquadro (niente
artigli tagliati); un pezzo che tocca due icone si divide pixel per pixel verso la più vicina,
così non restano avanzi delle vicine ai bordi. Salva assets/sprites/icons/<id>.png (128 px).
"""
import sys
from collections import deque
from pathlib import Path
from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "assets" / "sprites" / "icons"
BOXES = {   # (x0, y0, x1, y1) sul foglio 1774x887
    "claws_sharp": (30, 5, 385, 345), "claws_serrated": (395, 5, 725, 345),
    "claws_obsidian": (730, 5, 1065, 345), "collar_leather": (1070, 30, 1410, 335),
    "collar_stray": (1420, 30, 1774, 365), "collar_bell": (120, 325, 470, 610),
    "amulet_moon": (585, 305, 810, 615), "amulet_cateye": (930, 305, 1180, 615),
    "amulet_flame": (1300, 300, 1590, 625),
    "spell_claw_leap": (10, 605, 330, 887), "spell_spectral_claw": (318, 595, 600, 887),
    "spell_hiss": (590, 600, 895, 887), "spell_dark_sight": (895, 600, 1175, 887),
    "spell_shadow_cat": (1175, 600, 1480, 887), "spell_nine_lives": (1480, 595, 1774, 887),
}


CENTERS = {n: ((x0 + x1) / 2, (y0 + y1) / 2) for n, (x0, y0, x1, y1) in BOXES.items()}
NAMES = list(BOXES)
ALPHA = 12              # da qui un pixel fa parte di un'icona (alone compreso)


def nearest(x, y):
    """Indice dell'icona col centro più vicino (distanze normalizzate sul riquadro)."""
    best, bi = None, 0
    for i, n in enumerate(NAMES):
        x0, y0, x1, y1 = BOXES[n]
        cx, cy = CENTERS[n]
        d = ((x - cx) / (x1 - x0)) ** 2 + ((y - cy) / (y1 - y0)) ** 2
        if best is None or d < best:
            best, bi = d, i
    return bi


def main():
    src = Image.open(sys.argv[1]).convert("RGBA")
    only = set(sys.argv[2:]) or set(NAMES)
    w, h = src.size
    a = src.getchannel("A").load()
    near = [[nearest(x, y) for x in range(0, w, 4)] for y in range(0, h, 4)]   # griglia rada: basta
    owner = [[-1] * w for _ in range(h)]
    seen = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if seen[y][x] or a[x, y] <= ALPHA:
                continue
            seen[y][x] = True
            q, pix = deque([(x, y)]), []
            while q:
                px, py = q.popleft()
                pix.append((px, py))
                for nx, ny in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and a[nx, ny] > ALPHA:
                        seen[ny][nx] = True
                        q.append((nx, ny))
            votes = {}
            for px, py in pix:
                k = near[py // 4][px // 4]
                votes[k] = votes.get(k, 0) + 1
            top, n_top = max(votes.items(), key=lambda kv: kv[1])
            whole = n_top >= 0.85 * len(pix)          # quasi tutto di un'icona: tutto suo
            for px, py in pix:
                owner[py][px] = top if whole else near[py // 4][px // 4]
    OUT.mkdir(parents=True, exist_ok=True)
    for idx, name in enumerate(NAMES):
        if name not in only:
            continue
        xs, ys = [], []
        for y in range(h):
            row = owner[y]
            for x in range(w):
                if row[x] == idx:
                    xs.append(x)
                    ys.append(y)
        x0, y0, x1, y1 = min(xs), min(ys), max(xs) + 1, max(ys) + 1
        tile = src.crop((x0, y0, x1, y1))
        tp = tile.load()
        for y in range(y1 - y0):
            for x in range(x1 - x0):
                if owner[y0 + y][x0 + x] != idx:
                    tp[x, y] = (0, 0, 0, 0)
        side = max(tile.size) + 6                       # un filo di margine: niente bordi tagliati
        sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        sq.paste(tile, ((side - tile.width) // 2, (side - tile.height) // 2))
        sq.resize((128, 128), Image.LANCZOS).save(OUT / f"{name}.png")
        print(name, tile.size)


if __name__ == "__main__":
    main()
