"""Pannello dei comandi nella fascia nera a sinistra della stanza.

Con il controller PlayStation mostra le icone dei tasti (assets/sprites/pad, ritagliate con
tools/slice_pad_icons.py); con un pad Xbox i tasti come bottoni colorati; con mouse e
tastiera i tasti disegnati come tasti della tastiera.
"""
import pygame
from game import settings as s, gfx
from game.asset_manager import AssetManager
from game.input import InputManager
from game.sound import SoundManager

ICON_H = 26                      # riquadro delle icone (logico)
ICON_W = 40
ROW_H  = 34

# (testo, icona PlayStation, tasto Xbox, tasto tastiera)
_ROWS = [
    ("Muovi",    "stick_l",  "LS",       "WASD"),
    ("Mira",     "stick_r",  "RS",       "Mouse"),
    ("Attacco",  "square",   "X",        "Click"),
    ("Schivata", "cross",    "A",        "Spazio"),
    ("Parata",   "r1",       "RB",       "Shift"),
    ("Magia 1",  "triangle", "Y",        "F"),
    ("Magia 2",  "circle",   "B",        "R"),
    ("Pozione",  "l2",       "LT",       "Q"),
    ("Mappa",    "l1",       "LB",       "TAB"),
    ("Equip.",   "share",    "View",     "I"),
    ("Hub",      "down",     "Giù",      "G"),
    ("Pausa",    "options",  "Start",    "ESC"),
]
_XBOX_COLORS = {"A": (96, 176, 72), "B": (214, 70, 60), "X": (60, 120, 214), "Y": (226, 186, 50)}

_icons: dict = {}


def _icon(name: str, scale: float = 1.0):
    key = (name, scale)
    if key not in _icons:
        path = AssetManager.image_path(f"pad/{name}")
        if not path.exists():
            _icons[key] = None
        else:
            img = pygame.image.load(str(path)).convert_alpha()
            k   = min(ICON_W / img.get_width(), ICON_H / img.get_height()) * scale   # sta nel riquadro
            _icons[key] = gfx.fit(img, (round(img.get_width() * k), round(img.get_height() * k)))
    return _icons[key]


def _keycap(screen, text: str, cx: int, cy: int, font, color=None):
    """Tasto disegnato: rettangolo arrotondato col testo (tastiera o tasti Xbox)."""
    img = font.render(text, True, (235, 232, 240))
    if color is not None:                                   # tasto frontale Xbox: cerchio colorato
        r = ICON_H // 2
        pygame.draw.circle(screen, (20, 20, 26), (cx, cy), r + 1)
        pygame.draw.circle(screen, color, (cx, cy), r - 1, 3)
        screen.blit(img, img.get_rect(center=(cx, cy)))
        return
    w = max(ICON_H, img.get_width() + 12)
    rect = pygame.Rect(0, 0, w, ICON_H - 4)
    rect.center = (cx, cy)
    pygame.draw.rect(screen, (14, 13, 18), rect.move(0, 2), border_radius=5)
    pygame.draw.rect(screen, (46, 44, 54), rect, border_radius=5)
    pygame.draw.rect(screen, (90, 86, 104), rect, 1, border_radius=5)
    screen.blit(img, img.get_rect(center=rect.center))


# azione -> (icona PlayStation, tasto Xbox, tasto tastiera)
_BUTTONS = {
    "interact": ("cross", "A", "E"),
    "confirm":  ("cross", "A", "Invio"),
    "back":     ("circle", "B", "Esc"),
    "delete":   ("triangle", "Y", "Canc"),
    "second":   ("square", "X", "R"),
    "change":   ("left", "Croce", "Frecce"),
}


def draw_button(screen, action: str, cx: int, cy: int) -> int:
    """Un solo tasto centrato in (cx, cy), es. sopra un personaggio o nei suggerimenti di un
    menu. Restituisce la larghezza occupata."""
    if action not in _BUTTONS:
        return 0
    ps_icon, xbox_key, key = _BUTTONS[action]
    pad  = InputManager.get()
    font = AssetManager.get().font(13, bold=True)
    if pad.using_controller and pad.pad_style == "ps" and _icon(ps_icon) is not None:
        img = _icon(ps_icon, 0.8)
        screen.blit(img, img.get_rect(center=(cx, cy)))
        return img.get_width()
    if pad.using_controller:
        _keycap(screen, xbox_key, cx, cy, font, _XBOX_COLORS.get(xbox_key))
        return ICON_H if xbox_key in _XBOX_COLORS else max(ICON_H, font.size(xbox_key)[0] + 12)
    _keycap(screen, key, cx, cy, font)
    return max(ICON_H, font.size(key)[0] + 12)


def draw(screen, bar_w: int, top: int, highlight: str = None):
    """Disegna i comandi nella fascia larga bar_w a sinistra, a partire da y=top.
    highlight: riga da far pulsare (prima partita: "Muovi", "Attacco"...)."""
    if bar_w < 120:
        return
    pad   = InputManager.get()
    style = ("ps" if pad.pad_style == "ps" else "xbox") if pad.using_controller else "keys"
    from game.menu import _font, _spaced          # qui: menu importa questo modulo
    am    = AssetManager.get()
    label_font = _font(15)
    key_font   = am.font(13, bold=True)
    icon_cx    = 36
    text_x     = 68

    title = _spaced("COMANDI", _font(12, "bold"), (150, 140, 165), 4)
    screen.blit(title, title.get_rect(centerx=bar_w // 2, top=top))
    pygame.draw.line(screen, (60, 56, 70), (14, top + 20), (bar_w - 14, top + 20))

    rows = list(_ROWS)
    if style == "keys":
        rows.append(("Muto" if SoundManager.get().muted else "Audio", None, None, "M"))
    y = top + 30 + ROW_H // 2
    for text, ps_icon, xbox_key, key in rows:
        lit = text == highlight
        if lit:                                             # prima partita: questa riga respira
            import math
            k = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 1000.0 * 4.0)
            hl = gfx.Surface((bar_w - 12, ROW_H - 4), pygame.SRCALPHA)
            pygame.draw.rect(hl, (255, 184, 92, round(26 + 30 * k)), hl.get_rect(), border_radius=8)
            pygame.draw.rect(hl, (255, 184, 92, round(90 + 90 * k)), hl.get_rect(), 1, border_radius=8)
            screen.blit(hl, (6, y - (ROW_H - 4) // 2))
        if style == "ps" and _icon(ps_icon) is not None:
            img = _icon(ps_icon)
            screen.blit(img, img.get_rect(center=(icon_cx, y)))
            if ps_icon.startswith("stick"):                 # i due stick: L / R al centro
                side = key_font.render("L" if ps_icon == "stick_l" else "R", True, (200, 196, 210))
                screen.blit(side, side.get_rect(center=(icon_cx, y)))
        elif style == "xbox":
            _keycap(screen, xbox_key, icon_cx, y, key_font, _XBOX_COLORS.get(xbox_key))
        else:
            _keycap(screen, key, icon_cx, y, key_font)
        lbl = label_font.render(text, True, (255, 226, 180) if lit else (196, 190, 206))
        screen.blit(lbl, lbl.get_rect(midleft=(text_x, y)))
        if style == "ps" and text == "Attacco":          # anche R2 attacca: icona piccola in fondo
            r2 = _icon("r2", 0.85)
            if r2 is not None:
                screen.blit(r2, r2.get_rect(midleft=(text_x + lbl.get_width() + 8, y)))
        y += ROW_H
