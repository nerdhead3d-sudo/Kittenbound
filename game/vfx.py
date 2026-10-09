"""Effetti dipinti a fotogrammi: graffio, impatto, parata, fumo, polvere, aura, stelline.

I fotogrammi sono in assets/sprites/vfx/<nome>_<i>.png (ritagliati da tools/slice_vfx.py).
frame() li dà già scalati/ruotati (con cache); spawn/update/draw gestiscono una lista di
animazioni "una volta sola" in coordinate del mondo (la stanza e il gatto ne hanno una).
Se i file mancano, available() è False e il gioco usa gli effetti disegnati di prima.
"""
from pathlib import Path

import pygame

from game import gfx

_DIR = Path(__file__).resolve().parent.parent / "assets" / "sprites" / "vfx"
_raw: dict = {}
_cache: dict = {}
SLASH_AXIS = -42          # inclinazione dei graffi nel foglio (gradi, y verso il basso)


def _frames(name: str) -> list:
    if name not in _raw:
        frames, i = [], 0
        while (_DIR / f"{name}_{i}.png").exists():
            frames.append(pygame.image.load(str(_DIR / f"{name}_{i}.png")).convert_alpha())
            i += 1
        _raw[name] = frames
    return _raw[name]


def available(name: str) -> bool:
    return bool(_frames(name))


def count(name: str) -> int:
    return len(_frames(name))


def frame(name: str, i: int, width: int, angle: float = 0.0, flip: bool = False):
    """Fotogramma i largo `width` (logico), ruotato di `angle` gradi (antiorario, come
    pygame.transform.rotate) e specchiato in orizzontale se `flip`."""
    frames = _frames(name)
    i = max(0, min(len(frames) - 1, i))
    a = round(angle / 6) * 6 % 360                 # 60 rotazioni bastano, e la cache resta piccola
    key = (name, i, width, a, flip)
    if key not in _cache:
        raw = frames[i]
        img = gfx.fit(raw, (width, max(1, round(width * raw.get_height() / raw.get_width()))))
        if flip:
            img = pygame.transform.flip(img, True, False)
        if a:
            img = pygame.transform.rotate(img, a)
        if len(_cache) > 1500:
            _cache.clear()
        _cache[key] = img
    return _cache[key]


# ── Animazioni che si giocano una volta ───────────────────────────────────────

def spawn(lst: list, name: str, x: float, y: float, width: int, duration: float,
          angle: float = 0.0, flip: bool = False):
    if available(name):
        lst.append([name, x, y, width, 0.0, duration, angle, flip])


def update(lst: list, dt: float):
    for a in lst:
        a[4] += dt
    lst[:] = [a for a in lst if a[4] < a[5]]


def draw(lst: list, surface, cam):
    for name, x, y, width, age, dur, angle, flip in lst:
        img = frame(name, int(age / dur * count(name)), width, angle, flip)
        surface.blit(img, img.get_rect(center=(round(x - cam[0]), round(y - cam[1]))))


def loop_frame(name: str, t: float, fps: float, width: int):
    """Fotogramma di un'animazione in loop (aura, stelline)."""
    return frame(name, int(t * fps) % count(name), width)
