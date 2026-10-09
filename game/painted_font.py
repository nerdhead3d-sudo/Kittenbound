"""Font dipinto (lettere dorate con il bordo scuro) per i titoli.

I glifi sono in assets/fonts/painted (ritagliati da tools/slice_font.py). PaintedFont si usa
come un pygame.font.Font: render(testo, aa, colore) e size(testo); il colore è ignorato
(le lettere sono già dipinte). Le lettere accentate si compongono: lettera + accento.
"""
import json
from pathlib import Path

import pygame

from game import gfx

_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "painted"
_ACCENTS = {"à": "a", "è": "e", "é": "e", "ì": "i", "ò": "o", "ù": "u",
            "À": "A", "È": "E", "É": "E", "Ì": "I", "Ò": "O", "Ù": "U"}
_SUBST = {"—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "·": ".", "×": "x"}
_data = None
_glyphs = {}
_cache = {}


def available() -> bool:
    return (_DIR / "metrics.json").exists()


def _metrics():
    global _data
    if _data is None:
        _data = json.loads((_DIR / "metrics.json").read_text(encoding="utf-8"))
        g = _data["glyphs"]
        _data["asc"] = max(m["base"] for m in g.values())
        _data["desc"] = max(m["h"] - m["base"] for m in g.values())
    return _data


def _glyph(ch):
    if ch not in _glyphs:
        path = _DIR / f"{ord(ch)}.png"
        _glyphs[ch] = pygame.image.load(str(path)).convert_alpha() if path.exists() else None
    return _glyphs[ch]


def _render(text: str, cap: int):
    key = (text, cap)
    if key in _cache:
        return _cache[key]
    d = _metrics()
    g = d["glyphs"]
    src_cap = d["cap"]
    space = round(src_cap * 0.34)
    overlap = round(src_cap * 0.07)               # i bordi scuri si toccano un po'
    asc, desc = d["asc"], d["desc"]
    upper_acc = any(c in _ACCENTS and c.isupper() for c in text)
    lift = round(src_cap * 0.25) if upper_acc else 0   # spazio sopra per gli accenti delle maiuscole
    parts, x = [], 0
    for ch in text:
        base_ch = _ACCENTS.get(ch, _SUBST.get(ch, ch))
        if base_ch not in g or _glyph(base_ch) is None:
            x += space
            continue
        m = g[base_ch]
        parts.append((x, base_ch, m))
        if ch in _ACCENTS and "`" in g:                 # accento grave sopra la lettera
            top = asc + lift - m["base"]               # cima della lettera nella riga
            parts.append(("accent", x + m["w"] // 2, top, ch.isupper()))
        x += m["w"] - overlap
    width = max(1, x + overlap)
    height = asc + desc + lift
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    for p in parts:
        if p[0] == "accent":
            _, cx, top, upper = p
            acc = _glyph("`")
            k = 0.7
            a = pygame.transform.smoothscale(acc, (round(acc.get_width() * k), round(acc.get_height() * k)))
            surf.blit(a, a.get_rect(midbottom=(cx + round(src_cap * 0.05), top + round(src_cap * (0.12 if upper else 0.18)))))
            continue
        px, ch, m = p
        surf.blit(_glyph(ch), (px, asc + lift - m["base"]))
    k = cap / src_cap
    out = gfx.fit(surf, (max(1, round(width * k)), max(1, round(height * k))))
    _cache[key] = out
    return out


class PaintedFont:
    """Come pygame.font.Font, ma con le lettere dipinte. `size` = dimensione "tipografica"."""

    def __init__(self, size: int, scale: float = 0.62):
        self.px  = size
        self.cap = max(6, round(size * scale))

    def render(self, text, antialias=True, color=None, background=None):
        """Il colore non tinge (le lettere sono dipinte) ma un colore spento le scurisce:
        così nei menu la voce scelta resta brillante e le altre no."""
        surf = _render(str(text), self.cap)
        bright = 255 if color is None else max(color[:3])
        if bright >= 225:
            return surf.copy()                       # copia: chi la sfuma non tocca la cache
        key = (str(text), self.cap, "dim", bright // 16)
        if key not in _cache:
            k = max(90, min(255, round(bright * 1.05)))
            dim = surf.copy()
            dim.fill((k, k, k, 255), special_flags=pygame.BLEND_RGBA_MULT)
            _cache[key] = dim
        return _cache[key].copy()

    def size(self, text):
        return self.render(text).get_size()

    def get_height(self):
        return self.render("Ag").get_height()
