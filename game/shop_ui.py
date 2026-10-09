"""Negozi in stile moderno (Mago, Alchimista, Mercante): a sinistra la cosa scelta in grande,
a destra la lista, in basso i tasti come icone.

Le icone si cercano in assets/sprites/icons/<nome>.png; finché non ci sono si disegnano qui.
"""
import math

import pygame

from game import settings as s, gfx, equipment
from game.asset_manager import AssetManager
from game.input import InputManager

GOLD_OK  = (250, 210, 90)
GOLD_NO  = (150, 110, 60)
GREEN    = (130, 220, 150)
BLUEISH  = (150, 170, 210)
RED      = (240, 120, 110)

# colore dell'alone di ogni icona disegnata
COLORS = {
    "hp_max": (235, 70, 80), "hp_regen": (110, 220, 120), "energy_max": (90, 160, 255),
    "energy_regen": (120, 200, 255), "melee_dmg": (255, 190, 80), "potion": (230, 60, 70),
    "elixir": (250, 200, 80), "map": (220, 180, 120), "audacia": (255, 130, 50),
}

_cache = {}


def txt_font(size, kind="ui"):
    """Col pad serve il font coi simboli (△ ○ □ ✕); con la tastiera il carattere moderno."""
    from game.menu import _font
    if InputManager.get().using_controller:
        return AssetManager.get().ui_font(size, bold=kind != "ui")
    return _font(size, kind)


# ── Icone ─────────────────────────────────────────────────────────────────────

def _heart(d, cx, cy, r, col):
    pygame.draw.circle(d, col, (cx - r * 0.5, cy - r * 0.25), r * 0.55)
    pygame.draw.circle(d, col, (cx + r * 0.5, cy - r * 0.25), r * 0.55)
    pygame.draw.polygon(d, col, [(cx - r * 1.02, cy - r * 0.1), (cx + r * 1.02, cy - r * 0.1), (cx, cy + r * 0.95)])


def _bolt(d, cx, cy, r, col):
    pts = [(0.15, -1.0), (-0.55, 0.12), (-0.05, 0.12), (-0.25, 1.0), (0.55, -0.2), (0.05, -0.2), (0.3, -1.0)]
    pygame.draw.polygon(d, col, [(cx + x * r, cy + y * r) for x, y in pts])


def _bottle(d, cx, cy, r, col, light):
    pygame.draw.circle(d, (40, 30, 40), (cx, cy + r * 0.25), r * 0.72)
    pygame.draw.circle(d, col, (cx, cy + r * 0.25), r * 0.64)
    pygame.draw.rect(d, (210, 220, 230), (cx - r * 0.2, cy - r * 0.85, r * 0.4, r * 0.55))
    pygame.draw.rect(d, (150, 100, 60), (cx - r * 0.26, cy - r * 1.0, r * 0.52, r * 0.22), border_radius=3)
    pygame.draw.circle(d, light, (cx - r * 0.25, cy + r * 0.05), r * 0.16)


def _draw_kind(kind, size):
    """Icona disegnata a mano (4× e poi rimpicciolita, per i bordi morbidi)."""
    S = size * 4
    d = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S / 2
    r = S * 0.36
    if kind == "hp_max":
        _heart(d, c, c, r, (120, 20, 30))
        _heart(d, c, c - r * 0.06, r * 0.9, (235, 70, 80))
        pygame.draw.rect(d, (255, 240, 240), (c - r * 0.1, c - r * 0.55, r * 0.2, r * 0.8))
        pygame.draw.rect(d, (255, 240, 240), (c - r * 0.4, c - r * 0.25, r * 0.8, r * 0.2))
    elif kind == "hp_regen":
        _heart(d, c, c, r, (40, 100, 50))
        _heart(d, c, c - r * 0.06, r * 0.9, (110, 210, 110))
        for ang, dist, rr in ((-0.8, 1.05, 0.13), (0.4, 1.1, 0.1), (2.4, 1.0, 0.09)):
            x, y = c + math.cos(ang) * r * dist, c + math.sin(ang) * r * dist
            pygame.draw.polygon(d, (220, 255, 200), [(x, y - r * rr * 2), (x + r * rr * 0.6, y), (x, y + r * rr * 2), (x - r * rr * 0.6, y)])
    elif kind in ("energy_max", "energy_regen"):
        pygame.draw.polygon(d, (30, 60, 120), [(c, c - r * 1.1), (c + r * 0.75, c), (c, c + r * 1.1), (c - r * 0.75, c)])
        pygame.draw.polygon(d, (70, 140, 240), [(c, c - r * 0.98), (c + r * 0.64, c), (c, c + r * 0.98), (c - r * 0.64, c)])
        pygame.draw.polygon(d, (140, 200, 255), [(c, c - r * 0.98), (c + r * 0.64, c), (c, c)])
        _bolt(d, c, c, r * 0.62, (255, 255, 210))
        if kind == "energy_regen":
            for k in range(3):
                a0 = k * math.tau / 3
                pygame.draw.arc(d, (160, 230, 255), (c - r * 1.15, c - r * 1.15, r * 2.3, r * 2.3), a0, a0 + 1.2, max(2, S // 40))
    elif kind == "melee_dmg":
        pygame.draw.ellipse(d, (90, 60, 40), (c - r * 0.6, c - r * 0.05, r * 1.2, r * 0.95))
        pygame.draw.ellipse(d, (230, 190, 150), (c - r * 0.5, c + r * 0.05, r * 1.0, r * 0.78))
        for k, (dx, dy) in enumerate(((-0.62, -0.25), (-0.22, -0.55), (0.22, -0.55), (0.62, -0.25))):
            x, y = c + dx * r, c + dy * r
            pygame.draw.circle(d, (230, 190, 150), (x, y), r * 0.2)
            pygame.draw.polygon(d, (250, 245, 235), [(x - r * 0.08, y - r * 0.12), (x + r * 0.08, y - r * 0.12),
                                                     (x + dx * r * 0.25, y - r * 0.55)])
    elif kind == "potion":
        _bottle(d, c, c, r, (210, 40, 55), (255, 170, 170))
    elif kind == "elixir":
        _bottle(d, c, c, r, (235, 175, 50), (255, 245, 190))
    elif kind == "map":
        pygame.draw.rect(d, (120, 85, 50), (c - r * 0.95, c - r * 0.75, r * 1.9, r * 1.5), border_radius=S // 24)
        pygame.draw.rect(d, (230, 205, 150), (c - r * 0.88, c - r * 0.68, r * 1.76, r * 1.36), border_radius=S // 28)
        w = max(2, S // 50)
        pygame.draw.lines(d, (150, 100, 60), False, [(c - r * 0.7, c + r * 0.4), (c - r * 0.3, c - r * 0.1),
                                                     (c + r * 0.1, c + r * 0.2), (c + r * 0.5, c - r * 0.35)], w)
        pygame.draw.circle(d, (190, 40, 40), (c + r * 0.55, c - r * 0.38), r * 0.14)
    elif kind == "audacia":
        def drop(scale, col, dy=0.0):                    # goccia a punta in su
            pts = []
            for i in range(48):
                a = i / 48 * math.tau
                x = math.sin(a) * math.sin(a / 2) ** 1.3
                y = -math.cos(a)
                pts.append((c + x * r * 0.85 * scale, c + r * 0.25 + dy * r + y * r * scale))
            pygame.draw.polygon(d, col, pts)
        drop(1.0, (190, 50, 20))
        drop(0.86, (255, 120, 30), 0.1)
        drop(0.55, (255, 200, 70), 0.4)
        drop(0.28, (255, 245, 200), 0.62)
    else:
        pygame.draw.circle(d, (120, 110, 140), (c, c), r)
    return gfx.fit(d, (size, size))


def icon(kind: str, size: int):
    """Icona di un'offerta: dipinta se c'è (icons/<kind>.png), altrimenti disegnata."""
    key = (kind, size)
    if key not in _cache:
        if kind in equipment.ITEMS or kind.startswith("spell_"):
            _cache[key] = equipment.icon(kind, size)
        else:
            path = AssetManager.image_path(f"icons/{kind}")
            _cache[key] = (gfx.fit(pygame.image.load(str(path)).convert_alpha(), (size, size))
                           if path.exists() else _draw_kind(kind, size))
    return _cache[key]


def glow_color(kind: str):
    if kind in equipment.ITEMS:
        return equipment.ITEMS[kind].color
    return COLORS.get(kind, (200, 180, 255))


# ── Disegno ───────────────────────────────────────────────────────────────────

def wrap_center(surface, text, font, color, cx, y, width):
    line, lines = "", []
    for word in text.split():
        test = (line + " " + word).strip()
        if font.size(test)[0] > width and line:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    for ln in lines:
        img = font.render(ln, True, color)
        surface.blit(img, img.get_rect(centerx=cx, top=y))
        y += font.get_height() + 2
    return y


def coin(surface, cx, cy, r=8):
    img = equipment.icon("coin", 2 * r + 4)            # moneta dipinta, se c'è
    if img is not None:
        surface.blit(img, img.get_rect(center=(cx, cy)))
        return
    pygame.draw.circle(surface, (150, 100, 20), (cx + 1, cy + 1), r)
    pygame.draw.circle(surface, (250, 200, 70), (cx, cy), r)


def draw(surface, *, overline, title, gold, rows, sel, detail, hints, msg=None, accent=None, veil=246):
    """Disegna un negozio.

    rows:   [{"icon": Surface|None, "name": str, "sub": str|None, "tag": (testo, colore, moneta?),
              "dim": bool}]
    detail: {"icon": Surface|None, "color": rgb, "name": str, "desc": str,
             "line": (testo, colore)|None, "status": (testo, colore)|None}
    hints:  [(azione di controls_panel, etichetta)]
    msg:    (testo, alpha 0-1, errore?) oppure None
    """
    from game.menu import _font, _spaced, _panel, ACCENT, WHITE, MUTED
    from game import controls_panel
    accent = accent or ACCENT
    W, H = s.SCREEN_W, s.SCREEN_H
    t = pygame.time.get_ticks() / 1000.0
    v = gfx.Surface((W, H), pygame.SRCALPHA)
    v.fill((10, 8, 16, veil))
    surface.blit(v, (0, 0))

    # ── sinistra: la cosa scelta ──
    cx, cy = 330, 280
    col = detail.get("color", accent)
    glow = gfx.Surface((360, 360), pygame.SRCALPHA)
    for r in range(170, 0, -10):
        pygame.draw.circle(glow, (*col, round(40 * (1 - r / 170) ** 1.5)), (180, 180), r)
    surface.blit(glow, (cx - 180, cy - 180))
    art = detail.get("icon")
    if art is not None:
        surface.blit(art, art.get_rect(center=(cx, cy + round(4 * math.sin(t * 2)))))
    name = _font(36, "title").render(detail["name"], True, WHITE)
    if name.get_width() > 560:
        name = _font(28, "title").render(detail["name"], True, WHITE)
    surface.blit(name, name.get_rect(centerx=cx, top=420))
    y = wrap_center(surface, detail.get("desc", ""), _font(17), MUTED, cx, 468, 440)
    if detail.get("line"):
        text, c = detail["line"]
        img = _font(15, "bold").render(text, True, c)
        surface.blit(img, img.get_rect(centerx=cx, top=max(y + 8, 530)))
    if detail.get("status"):
        text, c = detail["status"]
        img = txt_font(20, "bold").render(text, True, c)
        surface.blit(img, img.get_rect(centerx=cx, top=566))
    if msg is not None:
        text, alpha, err = msg
        m = _font(17, "bold").render(text, True, RED if err else accent)
        m.set_alpha(round(255 * max(0.0, min(1.0, alpha))))
        surface.blit(m, m.get_rect(centerx=cx, top=610))

    # ── destra: la lista ──
    lx, lw = 690, 520
    surface.blit(_spaced(overline, _font(13, "bold"), accent, 5), (lx, 56))
    surface.blit(_font(40, "title").render(title, True, WHITE), (lx, 74))
    g = _font(20, "bold").render(str(gold), True, (250, 214, 110))
    gx = lx + lw - 10 - g.get_width()
    surface.blit(g, (gx, 92))
    coin(surface, gx - 14, 104)
    n = max(1, len(rows))
    row_h = 66 if n <= 6 else 56
    gap = 6
    y0 = 150
    for i, row in enumerate(rows):
        y = y0 + i * (row_h + gap)
        chosen = i == sel
        rect = pygame.Rect(lx - 12, y, lw, row_h)
        _panel(surface, rect, fill=(*accent, 30) if chosen else (24, 20, 34, 170),
               border=(*accent, 120) if chosen else (255, 255, 255, 28), radius=12)
        if chosen:
            pygame.draw.rect(surface, accent, (rect.x, rect.y + 14, 4, row_h - 28), border_radius=2)
        ic = row.get("icon")
        if ic is not None:
            if row.get("dim"):
                ic = ic.copy()
                ic.set_alpha(110)
            surface.blit(ic, ic.get_rect(center=(lx + 26, y + row_h // 2)))
        name_col = (WHITE if chosen else (205, 200, 215)) if not row.get("dim") else (120, 115, 130)
        nm = _font(20, "head").render(row["name"], True, name_col)
        if row.get("sub"):
            sub = _font(14).render(row["sub"], True, MUTED if not row.get("dim") else (100, 96, 110))
            surface.blit(nm, (lx + 62, y + row_h // 2 - nm.get_height() + 2))
            surface.blit(sub, (lx + 62, y + row_h // 2 + 2))
        else:
            surface.blit(nm, nm.get_rect(x=lx + 62, centery=y + row_h // 2))
        tag = row.get("tag")
        if tag:
            text, c, with_coin = tag
            img = (_font(17, "bold") if with_coin else txt_font(16, "bold")).render(text, True, c)
            right = rect.right - 18
            surface.blit(img, img.get_rect(right=right, centery=y + row_h // 2))
            if with_coin:
                coin(surface, right - img.get_width() - 13, y + row_h // 2, 6)

    # ── tasti ──
    x, y = lx, H - 50
    for action, label in hints:
        w = controls_panel.draw_button(surface, action, x + 14, y + 10)
        x += max(w, 28) + 8
        f = txt_font(16)
        surface.blit(f.render(label, True, MUTED), (x, y))
        x += f.size(label)[0] + 30
