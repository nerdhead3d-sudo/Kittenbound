"""Interfaccia in partita, stile pulito (come i menu di game/menu.py).

- Stato del gatto in alto a sinistra: medaglione del livello con l'esperienza come anello,
  barre di vita ed energia arrotondate, oro / pozioni / Audacia come icone con un numero,
  le 2 magie come caselle con l'icona dipinta.
- Barra del boss in basso al centro, col nome.
- Titolo del piano quando entri (poi sparisce), avvisi a centro schermo, schermate a scelta
  (pausa, morte, fine piano...) con i tasti come icone.
"""
import math

import pygame

from game import gfx, spells, equipment
from game import settings as s
from game import controls_panel
from game.asset_manager import AssetManager
from game.input import InputManager
from game.menu import _font, _spaced, _panel, ACCENT, WHITE, MUTED, DIM

HP_COL = (226, 72, 78)
EN_COL = (246, 196, 72)
XP_COL = (120, 200, 255)


def _bar(surface, x, y, w, h, pct, col):
    pygame.draw.rect(surface, (14, 12, 20), (x - 1, y - 1, w + 2, h + 2), border_radius=h)
    pygame.draw.rect(surface, (44, 40, 54), (x, y, w, h), border_radius=h)
    if pct > 0:
        fw = max(h, round(w * min(1.0, pct)))
        pygame.draw.rect(surface, col, (x, y, fw, h), border_radius=h)
        hi = tuple(min(255, c + 50) for c in col)
        pygame.draw.rect(surface, hi, (x + 3, y + 1, max(1, fw - 6), max(1, h // 3)), border_radius=h)


def _coin(surface, cx, cy, r=7):
    from game import equipment
    img = equipment.icon("coin", 2 * r + 4)            # moneta dipinta, se c'è
    if img is not None:
        surface.blit(img, img.get_rect(center=(cx, cy)))
        return
    pygame.draw.circle(surface, (150, 100, 20), (cx + 1, cy + 1), r)
    pygame.draw.circle(surface, (250, 200, 70), (cx, cy), r)
    pygame.draw.circle(surface, (255, 236, 150), (cx, cy), r - 3, 1)


_potion_icons = {}


def _potion_icon(full: bool):
    """Pozione dipinta (icons/potion.png) per l'HUD; vuota = la stessa scura e trasparente."""
    if full not in _potion_icons:
        from game import equipment
        img = equipment.icon("potion", 19)
        if img is not None and not full:
            img = img.copy()
            img.fill((80, 76, 92, 130), special_flags=pygame.BLEND_RGBA_MULT)
        _potion_icons[full] = img
    return _potion_icons[full]


def _potion(surface, cx, cy, full=True):
    img = _potion_icon(full)
    if img is not None:
        surface.blit(img, img.get_rect(center=(cx, cy - 1)))
        return
    body = (220, 50, 64) if full else (60, 56, 70)
    pygame.draw.rect(surface, (180, 150, 110) if full else (80, 76, 90), (cx - 2, cy - 9, 5, 4))
    pygame.draw.circle(surface, body, (cx, cy), 6)
    if full:
        pygame.draw.circle(surface, (255, 180, 180), (cx - 2, cy - 2), 2)


def _flame(surface, cx, cy, size, col, t):
    size = size + (math.sin(t * 9) * 0.6)
    pygame.draw.polygon(surface, col, [(cx - size * 0.7, cy), (cx + size * 0.7, cy), (cx, cy - size * 2)])
    pygame.draw.circle(surface, col, (cx, cy - 1), round(size * 0.75))
    pygame.draw.circle(surface, (255, 245, 210), (cx, cy - 1), max(1, round(size / 3)))


def draw_status(surface, player, spells_too: bool = True):
    """Stato del gatto in alto a sinistra."""
    t = pygame.time.get_ticks() / 1000.0
    x, y = 18, 16
    # medaglione del livello con l'anello dell'esperienza
    cx, cy, r = x + 26, y + 26, 24
    pygame.draw.circle(surface, (14, 12, 20), (cx, cy), r + 3)
    pygame.draw.circle(surface, (34, 30, 46), (cx, cy), r)
    pygame.draw.circle(surface, (60, 56, 74), (cx, cy), r, 3)
    if player.xp_pct > 0:
        pygame.draw.arc(surface, XP_COL, (cx - r, cy - r, 2 * r, 2 * r),
                        math.pi / 2 - 2 * math.pi * player.xp_pct, math.pi / 2, 3)
    lv = _font(22, "title").render(str(player.level), True, WHITE)
    surface.blit(lv, lv.get_rect(center=(cx, cy + 1)))

    bx = x + 60
    _bar(surface, bx, y + 8, 200, 12, player.hp_pct, HP_COL)
    _bar(surface, bx, y + 28, 160, 8, player.energy_pct, EN_COL)
    hp = _font(13, "bold").render(f"{int(player.hp)}", True, WHITE)
    surface.blit(hp, hp.get_rect(left=bx + 208, centery=y + 14))

    # oro, pozioni, Audacia
    row = y + 58
    _coin(surface, x + 10, row + 8)
    surface.blit(_font(16, "bold").render(str(player.gold), True, (250, 214, 110)), (x + 24, row - 1))
    px = x + 36 + _font(16, "bold").size(str(player.gold))[0] + 18
    for i in range(s.POTION_MAX):
        _potion(surface, px + i * 17, row + 9, i < player.potions)
    if player.audacia > 0:
        ax = px + s.POTION_MAX * 17 + 18
        tier = sum(1 for k in s.AUDACIA_TIERS if player.audacia >= k)
        col = [(255, 200, 90), (255, 200, 90), (255, 150, 50), (255, 90, 40), (255, 60, 160)][tier]
        _flame(surface, ax, row + 13, 4 + 3 * player.audacia / s.AUDACIA_MAX, col, t)
        surface.blit(_font(16, "bold").render(str(player.audacia), True, col), (ax + 10, row - 1))

    if spells_too:
        draw_spell_slots(surface, player, x, y + 90)


def draw_spell_slots(surface, player, x, y):
    """Le 2 magie: icona dipinta in una casella, tasto nell'angolo; scura se manca l'energia."""
    for i, sid in enumerate(player.spell_slots):
        rect = pygame.Rect(x + i * 52, y, 44, 44)
        sp = spells.SPELLS.get(sid) if sid else None
        ok = sp is not None and player.energy >= sp.cost
        _panel(surface, rect, fill=(20, 16, 30, 220), border=(*(sp.color if sp and ok else (80, 76, 94)), 200), radius=9)
        art = equipment.icon(f"spell_{sid}", 38) if sp else None
        if art is not None:
            art.set_alpha(255 if ok else 70)
            surface.blit(art, art.get_rect(center=rect.center))
        key = InputManager.get().label("F" if i == 0 else "R", "{Y}" if i == 0 else "{B}")
        k = AssetManager.get().ui_font(12, bold=True).render(key, True, WHITE)
        kb = pygame.Rect(0, 0, k.get_width() + 6, 15)
        kb.bottomright = (rect.right + 3, rect.bottom + 3)
        pygame.draw.rect(surface, (14, 12, 20), kb, border_radius=4)
        surface.blit(k, k.get_rect(center=kb.center))


def draw_boss_bar(surface, boss, name: str):
    w = 520
    x, y = (s.SCREEN_W - w) // 2, s.SCREEN_H - 50
    lbl = _spaced(name.upper(), _font(13, "bold"), (230, 210, 240), 4)
    surface.blit(lbl, lbl.get_rect(centerx=s.SCREEN_W // 2, bottom=y - 6))
    rage = getattr(boss, "_rage", False)
    _bar(surface, x, y, w, 12, boss.hp / max(1, boss.hp_max), (230, 110, 40) if rage else (200, 60, 90))
    rx = x + round(w * s.BOSS_RAGE_THRESHOLD)                # da qui in giù si arrabbia
    pygame.draw.line(surface, (255, 170, 80), (rx, y - 3), (rx, y + 14), 2)


def draw_banner(surface, title: str, sub: str, left: float, total: float):
    """Titolo del piano quando ci entri: appare, resta un attimo, sparisce."""
    k = min(1.0, (total - left) / 0.5, left / 0.8)
    if k <= 0:
        return
    t1 = _font(54, "title").render(title, True, WHITE)
    t2 = _spaced(sub.upper(), _font(15, "bold"), ACCENT, 6)
    for img in (t1, t2):
        img.set_alpha(round(255 * k))
    cy = s.SCREEN_H // 2 - 150
    surface.blit(t2, t2.get_rect(centerx=s.SCREEN_W // 2, bottom=cy - 4))
    surface.blit(t1, t1.get_rect(centerx=s.SCREEN_W // 2, top=cy))


def draw_notice(surface, notice):
    if notice is None:
        return
    text, col, left = notice
    img = _font(18, "head").render(text, True, col)
    pill = img.get_rect(centerx=s.SCREEN_W // 2, top=60).inflate(32, 14)
    layer = gfx.Surface(pill.size, pygame.SRCALPHA)
    pygame.draw.rect(layer, (12, 10, 18, 200), layer.get_rect(), border_radius=pill.h // 2)
    layer.blit(img, img.get_rect(center=layer.get_rect().center))
    layer.set_alpha(round(255 * min(1.0, left / 0.5)))
    surface.blit(layer, pill.topleft)


def modal(surface, title: str, subtitle: str, options: list, accent=ACCENT, extra: str = ""):
    """Schermata a scelta sopra il gioco: titolo, sottotitolo, opzioni come [tasto] testo."""
    veil = gfx.Surface((s.SCREEN_W, s.SCREEN_H), pygame.SRCALPHA)
    veil.fill((8, 6, 14, 190))
    surface.blit(veil, (0, 0))
    cx, cy = s.SCREEN_W // 2, s.SCREEN_H // 2
    t = _font(60, "title").render(title, True, WHITE)
    surface.blit(t, t.get_rect(centerx=cx, bottom=cy - 6))
    pygame.draw.rect(surface, accent, (cx - 32, cy + 6, 64, 4), border_radius=2)
    if subtitle:
        st = _font(18).render(subtitle, True, MUTED)
        surface.blit(st, st.get_rect(centerx=cx, top=cy + 24))
    if extra:
        ex = _font(16, "bold").render(extra, True, accent)
        surface.blit(ex, ex.get_rect(centerx=cx, top=cy + 54))
    # opzioni: misura e centra la riga
    f = _font(18, "head")
    widths = [36 + f.size(label)[0] for _, label in options]
    total = sum(widths) + 34 * (len(options) - 1)
    x, y = cx - total // 2, cy + (96 if extra else 72)
    for (action, label), w in zip(options, widths):
        bw = controls_panel.draw_button(surface, action, x + 14, y + f.get_height() // 2)
        surface.blit(f.render(label, True, WHITE), (x + max(bw, 28) + 8, y))
        x += w + 34


def merchant_icon(surface, cx, cy, r=8):
    """Icona del mercante nascosto: sacco viola con una moneta d'oro."""
    pygame.draw.circle(surface, (20, 12, 30), (cx, cy + 1), r + 2)
    pygame.draw.ellipse(surface, (150, 100, 220), (cx - r, cy - r * 0.6, r * 2, r * 1.7))
    pygame.draw.polygon(surface, (150, 100, 220), [(cx - r * 0.45, cy - r * 0.55), (cx + r * 0.45, cy - r * 0.55),
                                                   (cx + r * 0.2, cy - r), (cx - r * 0.2, cy - r)])
    pygame.draw.line(surface, (90, 60, 140), (cx - r * 0.5, cy - r * 0.55), (cx + r * 0.5, cy - r * 0.55), 2)
    pygame.draw.circle(surface, (250, 200, 70), (round(cx + r * 0.35), round(cy + r * 0.35)), max(2, r // 3))


def floor_entries(reached: dict) -> list:
    """Tutti i piani raggiunti, in ordine: [(bioma, piano), ...]."""
    out = []
    for b in range(1, len(s.BIOMES) + 1):
        out += [(b, f) for f in range(1, reached.get(str(b), 0) + 1)]
    return out


def draw_floor_select(surface, reached: dict, merchants: dict, sel: tuple, current: "tuple | None"):
    """Ingresso del dungeon: lista dei piani già raggiunti, raggruppati per bioma (scorre se
    sono tanti: i biomi possono aumentare)."""
    veil = gfx.Surface((s.SCREEN_W, s.SCREEN_H), pygame.SRCALPHA)
    veil.fill((8, 6, 14, 215))
    surface.blit(veil, (0, 0))
    cx = s.SCREEN_W // 2
    title = _font(48, "title").render("Dungeon", True, WHITE)
    surface.blit(title, title.get_rect(centerx=cx, top=86))
    pygame.draw.rect(surface, ACCENT, (cx - 32, 152, 64, 4), border_radius=2)

    # righe: un titoletto per ogni bioma, poi i suoi piani
    rows = []
    for b, f in floor_entries(reached):
        if not rows or rows[-1][1] != b:
            rows.append(("head", b, 0))
        rows.append(("floor", b, f))
    W, ROW, HEAD = 460, 50, 34
    heights = [HEAD if r[0] == "head" else ROW for r in rows]
    tops, y = [], 0
    for h in heights:
        tops.append(y)
        y += h
    sel_i = next((i for i, r in enumerate(rows) if r[0] == "floor" and (r[1], r[2]) == tuple(sel)), 0)
    view_top, view_h = 186, 400                                  # finestra visibile della lista
    scroll = max(0, min(tops[sel_i] - view_h // 2 + ROW, y - view_h)) if y > view_h else 0

    x0 = cx - W // 2
    for (kind, b, f), top, h in zip(rows, tops, heights):
        ry = view_top + top - scroll
        if ry < view_top - 2 or ry + h > view_top + view_h + 2:   # solo righe intere nella finestra
            continue
        if kind == "head":
            surface.blit(_spaced(s.BIOMES[b - 1]["name"].upper(), _font(13, "bold"), ACCENT, 4), (x0 + 4, ry + 12))
            continue
        rect = pygame.Rect(x0, ry + 3, W, ROW - 6)
        chosen = (b, f) == tuple(sel)
        _panel(surface, rect, fill=(44, 36, 60, 230) if chosen else (24, 20, 34, 200),
               border=(255, 184, 92, 255) if chosen else (255, 255, 255, 40), radius=10)
        if chosen:
            pygame.draw.rect(surface, ACCENT, (rect.x, rect.y + 10, 4, rect.h - 20), border_radius=2)
        lbl = _font(20, "head").render(f"Piano {f}", True, WHITE if chosen else (205, 200, 215))
        surface.blit(lbl, lbl.get_rect(x=rect.x + 20, centery=rect.centery))
        right = rect.right - 18
        if f"{b}-{f}" in merchants:                               # mercante trovato qui
            merchant_icon(surface, right - 6, rect.centery, 8)
            right -= 30
        if current is not None and tuple(current) == (b, f):      # partita in corso
            tag = _font(14, "bold").render("In corso", True, (130, 220, 150))
            surface.blit(tag, tag.get_rect(right=right, centery=rect.centery))
    if scroll > 0:                                                # c'è altro sopra / sotto
        pygame.draw.polygon(surface, MUTED, [(cx - 7, view_top - 8), (cx + 7, view_top - 8), (cx, view_top - 15)])
    if y - scroll > view_h:
        yb = view_top + view_h + 10
        pygame.draw.polygon(surface, MUTED, [(cx - 7, yb), (cx + 7, yb), (cx, yb + 7)])

    x, yh = cx - 150, s.SCREEN_H - 70
    for action, label in (("confirm", "Entra"), ("back", "Indietro")):
        w = controls_panel.draw_button(surface, action, x + 14, yh + 11)
        x += max(w, 28) + 8
        surface.blit(_font(17).render(label, True, MUTED), (x, yh))
        x += _font(17).size(label)[0] + 30
