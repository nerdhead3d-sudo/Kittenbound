"""Ritaglia la stanza dipinta delle Fogne (bioma 2) in pezzi per il gioco.

Uso (dalla root del progetto):
    python tools/slice_sewer_tiles.py <immagine.png> [--preview]

Stessa impaginazione della stanza del dungeon (1672x941, vista dall'alto, senza luci), con in
più i canali di liquame a croce, le grate e gli scarichi nei muri. Coordinate misurate sulle
fughe del pavimento (profilo di luminosità) e tra i blocchi del muro.

Pezzi salvati in assets/sprites/ con il prefisso sewer_ (normali e @2x), stessi nomi del
dungeon così il gioco li usa allo stesso modo:
    sewer_floor_dark_<i>, sewer_floor_light_<i>   piastrelle (scacchiera)
    sewer_slab_h<n>_<i>(_face), sewer_slab_v<n>_<i>, sewer_slab_p_<i>(_face)   muri e pilastri
In più, per le meccaniche delle fogne:
    sewer_water_<i>          acqua del canale (TILE x TILE)
    sewer_grate_<i>          grata nel pavimento (TILE x TILE): da qui spuntano i ratti
    sewer_channel_grate_<i>  grata sopra il canale
    sewer_drain_n, sewer_drain_w, sewer_drain_e   scarichi nel muro con la cascata d'acqua
"""
import sys
from pathlib import Path

import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent))
from slice_dungeon_tiles import OUT, T, H, luminance, save        # noqa: E402

P = "sewer_"

# ── Misure nell'immagine ──────────────────────────────────────────────────────
# fughe del pavimento; la prima e l'ultima colonna/riga sono in ombra sotto ai muri: escluse
FLOOR_X = [[298, 364, 429, 495, 562, 629, 697, 764], [907, 973, 1041, 1109, 1176, 1243, 1310, 1378]]
FLOOR_Y = [[175, 239, 302, 366], [540, 604, 669, 734, 796]]
PILLARS = [(559, 134, 71, 108), (1041, 194, 70, 108), (1244, 194, 71, 108),
           (560, 555, 70, 107), (1042, 555, 68, 107), (1310, 670, 68, 106)]
PILLAR_FACE_H = 32
GRATES = [(430, 303, 65, 63), (1178, 303, 65, 63), (430, 605, 65, 63), (1178, 605, 65, 63)]

TOP_Y, TOP_H   = 5, 77                        # cima del muro in alto
FACE_Y, FACE_H = 82, 35                       # mattoni sotto la cima
H_BLOCKS = [(230, 362, 2), (362, 439, 1), (439, 515, 1), (515, 682, 3), (682, 765, 1),
            (910, 994, 1), (994, 1157, 2), (1157, 1241, 1), (1241, 1346, 2), (1346, 1444, 1)]
V_COLUMNS = {"sx": (150, 232), "dx": (1445, 1525)}
V_BLOCKS  = [(75, 195, 2), (195, 270, 1), (270, 370, 2), (505, 620, 2), (620, 730, 2), (730, 805, 1)]

# canale orizzontale (y 447-511) e verticale (x 790-884): quadrati d'acqua lontani da grate e scarichi
WATER = [(x, 447, 64, 64) for x in (290, 354, 418, 570, 634, 698, 890, 954, 1018, 1180, 1244, 1308)] \
      + [(805, y, 64, 64) for y in (200, 264, 600, 664, 728)]
CHANNEL_GRATES = [(497, 443, 63, 72), (1112, 443, 63, 72), (790, 368, 95, 62), (790, 535, 95, 65)]
DRAINS = {"n": (765, 15, 145, 105), "w": (178, 385, 70, 130), "e": (1428, 385, 70, 130)}


def overlaps(x0, y0, x1, y1, boxes, margin=8, shadow=0) -> bool:
    return any(x0 < bx + bw + margin and x1 > bx - margin and y0 < by + bh + margin + shadow and y1 > by - margin
               for bx, by, bw, bh in boxes)


def main():
    pygame.init()
    pygame.display.set_mode((1, 1), pygame.HIDDEN)
    src = pygame.image.load(sys.argv[1]).convert_alpha()
    cut = lambda x, y, w, h: src.subsurface((x, y, w, h)).copy()   # noqa: E731
    for old in OUT.glob(f"{P}*.png"):                                 # pezzi del ritaglio precedente
        old.unlink()
    boxes = []                                                        # per l'anteprima

    # Pavimento: celle tra le fughe, lontane da muri, pilastri (e la loro ombra) e grate
    cells = []
    for xs in FLOOR_X:
        for ys in FLOOR_Y:
            for y0, y1 in zip(ys, ys[1:]):
                for x0, x1 in zip(xs, xs[1:]):
                    if overlaps(x0, y0, x1, y1, PILLARS, shadow=30) or overlaps(x0, y0, x1, y1, GRATES):
                        continue
                    r = (x0, y0, x1 - x0, y1 - y0)
                    cells.append((luminance(src.subsurface(r)), r))
    cells.sort()
    half = len(cells) // 2
    for kind, group in (("dark", cells[:half]), ("light", cells[half:])):
        for i, (_, r) in enumerate(group):
            save(f"{P}floor_{kind}_{i}", cut(*r), (T, T))
            boxes.append((r, (80, 200, 255)))

    # Muro in alto: blocchi da 1-3 tile con la loro striscia di mattoni
    count = {}
    for x0, x1, n in H_BLOCKS:
        i = count.get(n, 0)
        count[n] = i + 1
        save(f"{P}slab_h{n}_{i}", cut(x0, TOP_Y, x1 - x0, TOP_H), (n * T, T))
        save(f"{P}slab_h{n}_{i}_face", cut(x0, FACE_Y, x1 - x0, FACE_H), (n * T, H))
        boxes += [((x0, TOP_Y, x1 - x0, TOP_H), (255, 220, 60)), ((x0, FACE_Y, x1 - x0, FACE_H), (255, 120, 60))]

    # Muri laterali
    count = {}
    for x0, x1 in V_COLUMNS.values():
        for y0, y1, n in V_BLOCKS:
            i = count.get(n, 0)
            count[n] = i + 1
            save(f"{P}slab_v{n}_{i}", cut(x0, y0, x1 - x0, y1 - y0), (T, n * T))
            boxes.append(((x0, y0, x1 - x0, y1 - y0), (120, 255, 120)))

    # Pilastri: cima + mattoni
    for i, (px, py, pw, ph) in enumerate(PILLARS):
        top_h = ph - PILLAR_FACE_H
        save(f"{P}slab_p_{i}", cut(px, py, pw, top_h), (T, T))
        save(f"{P}slab_p_{i}_face", cut(px, py + top_h, pw, PILLAR_FACE_H), (T, H))
        boxes += [((px, py, pw, top_h), (255, 120, 255)), ((px, py + top_h, pw, PILLAR_FACE_H), (255, 60, 160))]

    # Acqua, grate, scarichi
    for i, r in enumerate(WATER):
        save(f"{P}water_{i}", cut(*r), (T, T))
        boxes.append((r, (60, 255, 200)))
    for i, r in enumerate(GRATES):
        save(f"{P}grate_{i}", cut(*r), (T, T))
        boxes.append((r, (255, 80, 80)))
    for i, r in enumerate(CHANNEL_GRATES):
        save(f"{P}channel_grate_{i}", cut(*r), (T, T))
        boxes.append((r, (255, 160, 80)))
    for side, r in DRAINS.items():
        k = H / FACE_H                                                # stessa scala dei mattoni
        save(f"{P}drain_{side}", cut(*r), (round(r[2] * k * 0.75), round(r[3] * k * 0.75)))
        boxes.append((r, (255, 255, 255)))

    print(f"pavimento {len(cells)}, muri in alto {len(H_BLOCKS)}, laterali {2 * len(V_BLOCKS)}, "
          f"pilastri {len(PILLARS)}, acqua {len(WATER)}, grate {len(GRATES)}+{len(CHANNEL_GRATES)}, scarichi {len(DRAINS)}")
    if "--preview" in sys.argv:
        dbg = src.copy()
        for r, col in boxes:
            pygame.draw.rect(dbg, col, r, 2)
        pygame.image.save(dbg, str(Path(sys.argv[1]).with_name("sewer_cuts_preview.png")))


if __name__ == "__main__":
    main()
