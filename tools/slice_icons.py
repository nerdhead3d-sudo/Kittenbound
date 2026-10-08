"""Ritaglia le icone di oggetti e magie dal foglio generato (sfondo trasparente).

Uso: python tools/slice_icons.py <foglio.png>
Ogni icona tiene i pezzi (zone collegate) che stanno quasi tutti nel suo riquadro; quelli
condivisi tra due icone che si toccano vengono tagliati lungo i riquadri. Salva assets/sprites/icons/<id>.png (128 px).
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


def owner(cx, cy):
    for name, (x0, y0, x1, y1) in BOXES.items():
        if x0 <= cx < x1 and y0 <= cy < y1:
            return name
    return None


def main():
    src = Image.open(sys.argv[1]).convert("RGBA")
    w, h = src.size
    a = src.getchannel("A").load()
    comp = [[-1] * w for _ in range(h)]
    owners = []
    for y in range(h):
        for x in range(w):
            if a[x, y] > 25 and comp[y][x] < 0:
                cid = len(owners)
                q, counts, n = deque([(x, y)]), {}, 0
                comp[y][x] = cid
                while q:
                    px, py = q.popleft()
                    o = owner(px, py)
                    counts[o] = counts.get(o, 0) + 1
                    n += 1
                    for nx, ny in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
                        if 0 <= nx < w and 0 <= ny < h and comp[ny][nx] < 0 and a[nx, ny] > 25:
                            comp[ny][nx] = cid
                            q.append((nx, ny))
                # pezzo di una sola icona -> suo; diviso tra più icone (si toccano) -> si taglia sui riquadri
                ranked = sorted(((v, k) for k, v in counts.items() if k), reverse=True)
                shared = len(ranked) > 1 and ranked[1][0] > 0.1 * n
                owners.append(None if (shared or not ranked) else ranked[0][1])
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (x0, y0, x1, y1) in BOXES.items():
        tile = src.crop((x0, y0, x1, y1))
        tp = tile.load()
        for y in range(y1 - y0):
            for x in range(x1 - x0):
                c = comp[y0 + y][x0 + x]
                if c >= 0 and owners[c] not in (name, None):
                    tp[x, y] = (0, 0, 0, 0)
                elif c < 0 and tp[x, y][3] and owner(x0 + x, y0 + y) != name:
                    tp[x, y] = (0, 0, 0, 0)
        tile = tile.crop(tile.getchannel("A").point(lambda v: 255 if v > 12 else 0).getbbox())
        side = max(tile.size)
        sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        sq.paste(tile, ((side - tile.width) // 2, (side - tile.height) // 2))
        sq.resize((128, 128), Image.LANCZOS).save(OUT / f"{name}.png")
        print(name, tile.size)


if __name__ == "__main__":
    main()
