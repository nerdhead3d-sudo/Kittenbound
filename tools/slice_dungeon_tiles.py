"""Ritaglia la stanza dipinta del dungeon in pezzi per il gioco.

Uso (dalla root del progetto):
    python tools/slice_dungeon_tiles.py <immagine.png> [--preview]

L'immagine è una stanza vista dall'alto (1672x941) senza luci dipinte: la luce delle torce
la aggiunge il gioco. Coordinate misurate sulle fughe del pavimento e tra i blocchi del muro.

Pezzi salvati in assets/sprites/ (ognuno normale e @2x per la grafica HD):
    floor_dark_<i>, floor_light_<i>   piastrelle (TILE x TILE): il pavimento è a scacchiera
    slab_h<n>_<i>   blocco del muro orizzontale lungo n tile (n*TILE x TILE), con
    slab_h<n>_<i>_face  la sua parete in mattoni (n*TILE x WALL_HEIGHT)
    slab_v<n>_<i>   blocco del muro verticale alto n tile (TILE x n*TILE)
    slab_p_<i>      blocco singolo (pilastro) e slab_p_<i>_face i suoi mattoni
    torch           torcia a muro (vedi torch_meta.json)
"""
import json
import sys
from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from game import settings as s                                   # noqa: E402

OUT = ROOT / "assets" / "sprites"
T, H = s.TILE_SIZE, s.WALL_HEIGHT

# ── Misure nell'immagine ──────────────────────────────────────────────────────
FLOOR_X = [298, 362, 425, 491, 559, 629, 698, 766, 835, 904, 972, 1041, 1110, 1179, 1248, 1316, 1384]
FLOOR_Y = [180, 242, 304, 366, 427, 488, 549, 608, 669, 729, 789]
CORRIDOR_X = (766, 904)                       # striscia più chiara davanti alle porte: esclusa
PILLARS = [(558, 138, 72, 109), (1040, 196, 72, 111), (1247, 196, 72, 111), (558, 505, 72, 110),
           (1040, 505, 72, 110), (1316, 567, 72, 110), (558, 687, 72, 110), (1316, 687, 72, 110)]

TOP_Y, TOP_H   = 5, 75                        # cima del muro in alto
FACE_Y, FACE_H = 81, 37                       # mattoni sotto la cima
# blocchi del muro in alto (x0, x1, quante tile valgono); quelli con la torcia dipinta sono esclusi
H_BLOCKS = [(711, 767, 1), (902, 959, 1), (229, 395, 2), (1280, 1443, 2), (514, 711, 3), (959, 1156, 3)]
# muri laterali (x0, x1) e blocchi (y0, y1, quante tile valgono)
V_COLUMNS = {"sx": (152, 232), "dx": (1443, 1524)}
V_BLOCKS = {"sx": [(392, 457, 1), (199, 283, 1), (77, 199, 2), (283, 392, 2), (556, 677, 2), (677, 809, 2)],
            "dx": [(199, 283, 1), (608, 677, 1), (77, 199, 2), (504, 608, 2), (677, 809, 2)]}
TORCH = (440, 18, 69, 103)                    # torcia in alto a sinistra con il muro attorno
TORCH_FACE_Y = FACE_Y                         # dove iniziano i mattoni nel ritaglio


def luminance(surf: pygame.Surface) -> float:
    w, h = surf.get_size()
    tot = n = 0
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            r, g, b, *_ = surf.get_at((x, y))
            tot += 0.3 * r + 0.59 * g + 0.11 * b
            n += 1
    return tot / n


def save(name: str, piece: pygame.Surface, size: tuple):
    for suffix, k in (("", 1), ("@2x", 2)):
        img = pygame.transform.smoothscale(piece, (size[0] * k, size[1] * k))
        pygame.image.save(img, str(OUT / f"{name}{suffix}.png"))


def overlaps_pillar(x0, y0, x1, y1, margin=8) -> bool:
    return any(x0 < px + pw + margin and x1 > px - margin and y0 < py + ph + margin and y1 > py - margin
               for px, py, pw, ph in PILLARS)


def main():
    pygame.init()
    pygame.display.set_mode((1, 1), pygame.HIDDEN)
    src = pygame.image.load(sys.argv[1]).convert_alpha()
    cut = lambda x, y, w, h: src.subsurface((x, y, w, h)).copy()   # noqa: E731
    for old in OUT.glob("*.png"):                                     # pezzi del ritaglio precedente
        if old.stem.startswith(("floor_", "slab_", "wall_top_", "wall_face_")):
            old.unlink()
    boxes = []                                                        # per l'anteprima

    # Pavimento: celle tra le fughe, lontane da muri, pilastri e corridoio; scure e chiare
    cells = []
    for y0, y1 in zip(FLOOR_Y[1:-2], FLOOR_Y[2:-1]):
        for x0, x1 in zip(FLOOR_X[1:-1], FLOOR_X[2:]):
            if CORRIDOR_X[0] <= x0 < CORRIDOR_X[1] or overlaps_pillar(x0, y0, x1, y1):
                continue
            r = (x0, y0, x1 - x0, y1 - y0)
            cells.append((luminance(src.subsurface(r)), r))
    cells.sort()
    half = len(cells) // 2
    for kind, group in (("dark", cells[:half]), ("light", cells[half:])):
        for i, (_, r) in enumerate(group):
            save(f"floor_{kind}_{i}", cut(*r), (T, T))
            boxes.append((r, (80, 200, 255)))

    # Muro orizzontale: blocchi da 1-3 tile con la loro striscia di mattoni
    count = {}
    for x0, x1, n in H_BLOCKS:
        i = count.get(n, 0)
        count[n] = i + 1
        save(f"slab_h{n}_{i}", cut(x0, TOP_Y, x1 - x0, TOP_H), (n * T, T))
        save(f"slab_h{n}_{i}_face", cut(x0, FACE_Y, x1 - x0, FACE_H), (n * T, H))
        boxes += [((x0, TOP_Y, x1 - x0, TOP_H), (255, 220, 60)), ((x0, FACE_Y, x1 - x0, FACE_H), (255, 120, 60))]

    # Muri laterali: blocchi alti 1-2 tile
    count = {}
    for side, (x0, x1) in V_COLUMNS.items():
        for y0, y1, n in V_BLOCKS[side]:
            i = count.get(n, 0)
            count[n] = i + 1
            save(f"slab_v{n}_{i}", cut(x0, y0, x1 - x0, y1 - y0), (T, n * T))
            boxes.append(((x0, y0, x1 - x0, y1 - y0), (120, 255, 120)))

    # Pilastri: cima quadrata + mattoni
    for i, (px, py, pw, ph) in enumerate(PILLARS):
        top_h = ph - FACE_H
        save(f"slab_p_{i}", cut(px, py, pw, top_h), (T, T))
        save(f"slab_p_{i}_face", cut(px, py + top_h, pw, FACE_H), (T, H))
        boxes += [((px, py, pw, top_h), (255, 120, 255)), ((px, py + top_h, pw, FACE_H), (255, 60, 160))]

    # Torcia: stessa scala dei mattoni, così la parete combacia con la tile
    tx, ty, tw, th = TORCH
    k = H / FACE_H
    tsize = (round(tw * k), round(th * k))
    save("torch", cut(*TORCH), tsize)
    (OUT / "torch_meta.json").write_text(json.dumps(
        {"face_y": round((TORCH_FACE_Y - ty) * k), "w": tsize[0], "h": tsize[1]}))
    boxes.append((TORCH, (255, 255, 255)))

    print(f"pavimento {len(cells)}, muri orizzontali {len(H_BLOCKS)}, "
          f"laterali {sum(len(v) for v in V_BLOCKS.values())}, pilastri {len(PILLARS)}, torcia 1")
    if "--preview" in sys.argv:
        dbg = src.copy()
        for r, col in boxes:
            pygame.draw.rect(dbg, col, r, 2)
        pygame.image.save(dbg, str(Path(sys.argv[1]).with_name("cuts_preview.png")))


if __name__ == "__main__":
    main()
