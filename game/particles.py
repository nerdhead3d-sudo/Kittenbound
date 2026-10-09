"""Particelle leggere della stanza: scintille sui colpi, sbuffo di polvere alla morte.

Vivono in room.particles; si creano con burst(), avanzano con update() e si disegnano
con draw() sopra i personaggi (prima del buio).
"""
import math
import random

import pygame

from game import gfx

# kind → (quante scintille, velocità, colori, quanti sbuffi)
_KINDS = {
    "hit":   (6,  (140, 260), [(255, 240, 200), (255, 210, 120)], 0),
    "crit":  (14, (200, 380), [(255, 250, 220), (255, 170, 60), (255, 120, 40)], 0),
    "death": (8,  (90, 200),  [(230, 220, 200), (200, 170, 130)], 9),
    "boss":  (26, (160, 420), [(255, 240, 200), (255, 170, 60)], 22),
}
MAX = 260
_puff_cache = {}


def _puff(r: int):
    """Sbuffo morbido (bianco, si tinge e sfuma al disegno)."""
    if r not in _puff_cache:
        surf = gfx.Surface((r * 2, r * 2), pygame.SRCALPHA)
        for k in range(r, 0, -1):
            a = round(150 * (1 - k / r) ** 0.8)
            pygame.draw.circle(surf, (120, 108, 96, a), (r, r), k)
        _puff_cache[r] = surf
    return _puff_cache[r]


def burst(room, x: float, y: float, kind: str = "hit"):
    sparks, (v0, v1), colors, puffs = _KINDS[kind]
    parts = room.__dict__.setdefault("particles", [])
    for _ in range(sparks):
        a = random.uniform(0, math.tau)
        v = random.uniform(v0, v1)
        life = random.uniform(0.2, 0.36)
        parts.append(["spark", x, y, math.cos(a) * v, math.sin(a) * v * 0.75, 0.0, life, random.choice(colors)])
    for _ in range(puffs):
        a = random.uniform(0, math.tau)
        v = random.uniform(15, 60)
        life = random.uniform(0.45, 0.8)
        parts.append(["puff", x + random.uniform(-8, 8), y + random.uniform(-6, 6),
                      math.cos(a) * v, math.sin(a) * v * 0.5 - 18, 0.0, life, random.randint(7, 13)])
    if len(parts) > MAX:
        del parts[:len(parts) - MAX]


def update(room, dt: float):
    parts = room.__dict__.get("particles")
    if not parts:
        return
    keep = []
    for p in parts:
        p[5] += dt
        if p[5] >= p[6]:
            continue
        drag = 0.86 if p[0] == "spark" else 0.93
        f = drag ** (dt * 60)
        p[3] *= f
        p[4] *= f
        p[1] += p[3] * dt
        p[2] += p[4] * dt
        keep.append(p)
    room.particles = keep


def draw(room, surface, cam):
    parts = room.__dict__.get("particles")
    if not parts:
        return
    cx, cy = cam
    for p in parts:
        k = p[5] / p[6]
        x, y = p[1] - cx, p[2] - cy
        if p[0] == "spark":
            ln = 0.05 * (1 - k)                       # scia lungo la velocità
            x0, y0 = x - p[3] * ln, y - p[4] * ln
            col = p[7]
            pygame.draw.line(surface, col, (round(x0), round(y0)), (round(x), round(y)), 2 if k < 0.5 else 1)
        else:
            r = round(p[7] * (0.7 + 0.8 * k))
            img = _puff(r)
            img.set_alpha(round(255 * (1 - k) ** 1.5))
            surface.blit(img, (round(x) - r, round(y) - r))
