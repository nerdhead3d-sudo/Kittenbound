"""Toglie lo sfondo a scacchi "finto" (grigio/bianco disegnato nell'immagine) dalle
illustrazioni generate, partendo dai bordi: le parti chiare interne restano.

Uso: python tools/remove_checker_bg.py <in.png> <out.png> [larghezza_max]
"""
import sys
from collections import deque
from PIL import Image


def is_bg(p):
    r, g, b = p[:3]
    return min(r, g, b) > 190 and max(r, g, b) - min(r, g, b) < 20


def main():
    src = Image.open(sys.argv[1]).convert("RGBA")
    w, h = src.size
    px = src.load()
    bg = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if is_bg(px[x, y]) and not bg[y * w + x]:
                bg[y * w + x] = 1; q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if is_bg(px[x, y]) and not bg[y * w + x]:
                bg[y * w + x] = 1; q.append((x, y))
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not bg[ny * w + nx] and is_bg(px[nx, ny]):
                bg[ny * w + nx] = 1
                q.append((nx, ny))
    # alone chiaro attorno alla sagoma: via anche i pixel chiari e grigi che toccano lo sfondo
    for _ in range(2):
        edge = []
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                if bg[y * w + x]:
                    continue
                if bg[y * w + x - 1] or bg[y * w + x + 1] or bg[(y - 1) * w + x] or bg[(y + 1) * w + x]:
                    r, g, b = px[x, y][:3]
                    if min(r, g, b) > 150 and max(r, g, b) - min(r, g, b) < 30:
                        edge.append(y * w + x)
        for i in edge:
            bg[i] = 1
    for y in range(h):
        for x in range(w):
            if bg[y * w + x]:
                px[x, y] = (0, 0, 0, 0)
    # bordo morbido: i pixel al confine diventano semitrasparenti
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if not bg[y * w + x]:
                n = bg[y * w + x - 1] + bg[y * w + x + 1] + bg[(y - 1) * w + x] + bg[(y + 1) * w + x]
                if n:
                    r, g, b, a = px[x, y]
                    px[x, y] = (r, g, b, round(a * (1 - 0.2 * n)))
    out = src.crop(src.getchannel("A").getbbox())
    if len(sys.argv) > 3:
        mw = int(sys.argv[3])
        if out.width > mw:
            out = out.resize((mw, round(out.height * mw / out.width)), Image.LANCZOS)
    out.save(sys.argv[2])
    print(out.size)


if __name__ == "__main__":
    main()
