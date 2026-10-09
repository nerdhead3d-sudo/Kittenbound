"""Ritaglia le icone da un foglio a griglia con lo sfondo sfumato (alone colorato, non
trasparente): per ogni casella toglie lo sfondo partendo dai bordi e allargandosi finché il
colore cambia poco da un pixel all'altro; si ferma sui contorni scuri e sui dettagli.

Uso:
    python tools/cut_glow_icons.py <foglio.png> <colonne> <righe> nome1 nome2 ... [--tol=12]
Le caselle si leggono per righe; "-" salta una casella; "nome!" = contorno scuro rigido (per
icone dall'interno liscio che lo sfondo svuoterebbe). Output: assets/sprites/icons/<nome>.png
"""
import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "assets" / "sprites" / "icons"


def _main_parts(bg, w, h, margin=1):
    """Pezzi dell'icona da tenere: il più grande, più le scintille staccate che non toccano
    il bordo della casella (quelle sul bordo sono avanzi delle icone vicine)."""
    seen = bytearray(w * h)
    parts = []
    for start in range(w * h):
        if bg[start] or seen[start]:
            continue
        seen[start] = 1
        q, pix, edge = deque([start]), [], False
        while q:
            i = q.popleft()
            pix.append(i)
            x, y = i % w, i // w
            if x < margin or y < margin or x >= w - margin or y >= h - margin:   # sul bordo
                edge = True
            for j in (i - 1 if x else -1, i + 1 if x < w - 1 else -1, i - w, i + w):
                if 0 <= j < w * h and not bg[j] and not seen[j]:
                    seen[j] = 1
                    q.append(j)
        parts.append((pix, edge))
    keep = bytearray(w * h)
    if not parts:
        return keep
    big = max(len(p) for p, _ in parts)
    for pix, edge in parts:
        if len(pix) == big or (not edge and len(pix) >= 30):
            for i in pix:
                keep[i] = 1
    return keep


def cut(cell: Image.Image, tol: float, strict: bool = False) -> Image.Image:
    """strict: il contorno scuro ferma sempre lo sfondo (meglio per icone con l'interno liscio,
    ma lascia macchie dove anche lo sfondo è scuro)."""
    w, h = cell.size
    soft = cell.convert("RGB").filter(ImageFilter.GaussianBlur(1.6))
    px = soft.load()
    bg = bytearray(w * h)
    q = deque()

    def lum(p):
        return 0.3 * p[0] + 0.59 * p[1] + 0.11 * p[2]

    for x in range(w):
        for y in (0, h - 1):
            q.append((x, y)); bg[y * w + x] = 1
    for y in range(h):
        for x in (0, w - 1):
            q.append((x, y)); bg[y * w + x] = 1
    while q:
        x, y = q.popleft()
        c = px[x, y]
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not bg[ny * w + nx]:
                n = px[nx, ny]
                if lum(n) < 45 and (strict or lum(c) >= 45):   # dal chiaro non si entra nello scuro
                    continue
                if abs(n[0] - c[0]) + abs(n[1] - c[1]) + abs(n[2] - c[2]) <= tol:
                    bg[ny * w + nx] = 1
                    q.append((nx, ny))
    keep = _main_parts(bg, w, h, 8 if strict else 1)
    mask = Image.new("L", (w, h), 0)
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            if keep[y * w + x]:
                mp[x, y] = 255
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(5))   # chiude i buchini
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    out = cell.convert("RGBA")
    out.putalpha(mask)
    box = mask.point(lambda v: 255 if v > 24 else 0).getbbox()
    if box:
        out = out.crop(box)
    side = max(out.size)                               # quadrata, centrata
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(out, ((side - out.width) // 2, (side - out.height) // 2))
    return sq


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tol = float(next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--tol=")), 12))
    sheet = Image.open(args[0]).convert("RGBA")
    cols, rows = int(args[1]), int(args[2])
    names = args[3:]
    cw, ch = sheet.width // cols, sheet.height // rows
    OUT.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(names):
        if name == "-":
            continue
        c, r = i % cols, i // cols
        strict = name.endswith("!")
        name = name.rstrip("!")
        icon = cut(sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)), tol, strict)
        icon.save(OUT / f"{name}.png")
        print(f"{name}: {icon.size}")


if __name__ == "__main__":
    main()
