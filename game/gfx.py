"""Grafica HD.

Il gioco ragiona sempre in coordinate logiche (1280x720: posizioni, collisioni, dimensioni degli
sprite), ma su schermi grandi disegna a K volte la risoluzione (K = 2 su 2560x1440), così testo,
sprite, sfondi e forme restano nitidi invece di essere ingranditi a blocchi.

Come funziona: con K > 1 ogni superficie del gioco è un `Canvas`, che espone le dimensioni logiche
ma contiene un'immagine K volte più grande (`.hi`). Le funzioni di pygame.draw e pygame.transform,
il mouse e i font vengono adattati qui una volta sola, quindi il codice di disegno resta scritto
in coordinate logiche e non deve sapere nulla della risoluzione reale.
Con K = 1 non cambia niente: `Surface()` restituisce una normale pygame.Surface.
"""
import os
import pygame

K = 1                                    # fattore di risoluzione (impostato da setup)

_DRAW = {n: getattr(pygame.draw, n) for n in
         ("rect", "circle", "ellipse", "line", "lines", "polygon", "arc", "aaline", "aalines")}
_TF   = {n: getattr(pygame.transform, n) for n in ("scale", "smoothscale", "flip", "rotate", "rotozoom")}
_MASK_FROM_SURFACE = pygame.mask.from_surface
_MOUSE_GET_POS     = pygame.mouse.get_pos


def setup(logical_size: tuple) -> int:
    """Sceglie K in base allo schermo (KITTEN_HD=1/2/3 per forzarlo) e attiva l'adattamento."""
    global K
    forced = os.environ.get("KITTEN_HD")
    if forced:
        K = max(1, int(forced))
    else:
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except (pygame.error, IndexError):
            dw, dh = logical_size
        K = max(1, min(dw // logical_size[0], dh // logical_size[1]))
    if K > 1:
        _install()
    return K


# ── Superficie HD ─────────────────────────────────────────────────────────────

class Canvas:
    """Superficie con dimensioni logiche, disegnata a K volte la risoluzione in `.hi`."""
    __slots__ = ("hi", "_w", "_h", "__weakref__")

    def __init__(self, size=None, flags=0, *args, hi: pygame.Surface = None):
        if hi is None:
            w, h = int(size[0]), int(size[1])
            hi = pygame.Surface((max(1, w * K), max(1, h * K)), flags, *args)
        elif size is None:
            w, h = -(-hi.get_width() // K), -(-hi.get_height() // K)
        else:
            w, h = int(size[0]), int(size[1])
        self.hi, self._w, self._h = hi, w, h

    # dimensioni (logiche)
    def get_size(self):
        return self._w, self._h

    def get_width(self):
        return self._w

    def get_height(self):
        return self._h

    def get_rect(self, **kw):
        r = pygame.Rect(0, 0, self._w, self._h)
        for k, v in kw.items():
            setattr(r, k, v)
        return r

    # disegno
    def blit(self, source, dest=(0, 0), area=None, special_flags=0):
        x, y = (dest.x, dest.y) if isinstance(dest, pygame.Rect) else (dest[0], dest[1])
        src, sw, sh = _hi_of(source)
        hi_area = None
        if area is not None:
            a = pygame.Rect(area)
            hi_area = pygame.Rect(a.x * K, a.y * K, a.w * K, a.h * K)
            sw, sh = a.w, a.h
        self.hi.blit(src, (round(x * K), round(y * K)), hi_area, special_flags)
        return pygame.Rect(int(x), int(y), sw, sh)

    def fill(self, color, rect=None, special_flags=0):
        self.hi.fill(color, _scale_rect(rect) if rect is not None else None, special_flags)
        return pygame.Rect(rect) if rect is not None else self.get_rect()

    def copy(self):
        return Canvas((self._w, self._h), hi=self.hi.copy())

    def subsurface(self, rect):
        r = pygame.Rect(rect)
        return Canvas(r.size, hi=self.hi.subsurface(_scale_rect(r)))

    def convert(self, *args):
        return Canvas((self._w, self._h), hi=self.hi.convert(*args))

    def convert_alpha(self, *args):
        return Canvas((self._w, self._h), hi=self.hi.convert_alpha(*args))

    def get_bounding_rect(self, min_alpha=1):
        r = self.hi.get_bounding_rect(min_alpha)
        x, y = r.x // K, r.y // K
        return pygame.Rect(x, y, -(-r.right // K) - x, -(-r.bottom // K) - y)

    def get_at(self, pos):
        return self.hi.get_at((int(pos[0] * K), int(pos[1] * K)))

    def set_alpha(self, *args):
        self.hi.set_alpha(*args)

    def get_alpha(self):
        return self.hi.get_alpha()

    def set_colorkey(self, *args):
        self.hi.set_colorkey(*args)

    def __getattr__(self, name):                  # get_flags, get_bitsize, lock, ...
        return getattr(self.hi, name)


def Surface(size, flags=0, *args):
    """Da usare al posto di pygame.Surface: HD quando K > 1."""
    if K > 1:
        return Canvas(size, flags, *args)
    return pygame.Surface(size, flags, *args)


def from_image(img: pygame.Surface, img_scale: int = 1):
    """Immagine caricata da file disegnata a img_scale volte la sua dimensione logica
    (es. sprite @2x: img_scale=2). Restituisce una superficie alla risoluzione giusta."""
    lw, lh = max(1, img.get_width() // img_scale), max(1, img.get_height() // img_scale)
    if K == 1:
        return img if img_scale == 1 else _TF["smoothscale"](img, (lw, lh))
    hi = img if img_scale == K else _TF["smoothscale"](img, (lw * K, lh * K))
    return Canvas((lw, lh), hi=hi)


def fit(img: pygame.Surface, size: tuple):
    """Immagine grande (es. sfondo dipinto) ridimensionata alla dimensione logica `size`,
    ricampionata una volta sola direttamente alla risoluzione reale."""
    if K == 1:
        return _TF["smoothscale"](img, size)
    return Canvas(size, hi=_TF["smoothscale"](img, (size[0] * K, size[1] * K)))


def wrap_display(display: pygame.Surface, logical_size: tuple):
    return display if K == 1 else Canvas(logical_size, hi=display)


def hi_surface(surface) -> pygame.Surface:
    """La superficie reale (per salvare screenshot)."""
    return surface.hi if isinstance(surface, Canvas) else surface


# ── Adattamento di pygame.draw / transform / mask / mouse ─────────────────────

def _hi_of(source):
    if isinstance(source, Canvas):
        return source.hi, source._w, source._h
    w, h = source.get_size()                      # superficie normale: ingrandita al volo
    return _TF["scale"](source, (w * K, h * K)), w, h


def _scale_rect(rect) -> pygame.Rect:
    if isinstance(rect, pygame.Rect):
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
    elif len(rect) == 2:
        (x, y), (w, h) = rect
    else:
        x, y, w, h = rect
    return pygame.Rect(round(x * K), round(y * K), round(w * K), round(h * K))


def _pt(p):
    return (p[0] * K, p[1] * K)


def _width(w):
    return 0 if w <= 0 else max(1, round(w * K))


def _down(r: pygame.Rect) -> pygame.Rect:
    return pygame.Rect(r.x // K, r.y // K, -(-r.w // K), -(-r.h // K))


def _rect(surface, color, rect, width=0, border_radius=0, *args, **kw):
    if not isinstance(surface, Canvas):
        return _DRAW["rect"](surface, color, rect, width, border_radius, *args, **kw)
    kw = {k: (v * K if v > 0 else v) for k, v in kw.items()}
    args = tuple(v * K if v > 0 else v for v in args)
    return _down(_DRAW["rect"](surface.hi, color, _scale_rect(rect), _width(width),
                               round(border_radius * K), *args, **kw))


def _circle(surface, color, center, radius, width=0, *args, **kw):
    if not isinstance(surface, Canvas):
        return _DRAW["circle"](surface, color, center, radius, width, *args, **kw)
    return _down(_DRAW["circle"](surface.hi, color, _pt(center), radius * K, _width(width), *args, **kw))


def _ellipse(surface, color, rect, width=0):
    if not isinstance(surface, Canvas):
        return _DRAW["ellipse"](surface, color, rect, width)
    return _down(_DRAW["ellipse"](surface.hi, color, _scale_rect(rect), _width(width)))


def _arc(surface, color, rect, start_angle, stop_angle, width=1):
    if not isinstance(surface, Canvas):
        return _DRAW["arc"](surface, color, rect, start_angle, stop_angle, width)
    return _down(_DRAW["arc"](surface.hi, color, _scale_rect(rect), start_angle, stop_angle, _width(width)))


def _line(surface, color, start_pos, end_pos, width=1):
    if not isinstance(surface, Canvas):
        return _DRAW["line"](surface, color, start_pos, end_pos, width)
    return _down(_DRAW["line"](surface.hi, color, _pt(start_pos), _pt(end_pos), _width(width)))


def _lines(surface, color, closed, points, width=1):
    if not isinstance(surface, Canvas):
        return _DRAW["lines"](surface, color, closed, points, width)
    return _down(_DRAW["lines"](surface.hi, color, closed, [_pt(p) for p in points], _width(width)))


def _polygon(surface, color, points, width=0):
    if not isinstance(surface, Canvas):
        return _DRAW["polygon"](surface, color, points, width)
    return _down(_DRAW["polygon"](surface.hi, color, [_pt(p) for p in points], _width(width)))


def _aaline(surface, color, start_pos, end_pos, *args):
    if not isinstance(surface, Canvas):
        return _DRAW["aaline"](surface, color, start_pos, end_pos, *args)
    return _down(_DRAW["line"](surface.hi, color, _pt(start_pos), _pt(end_pos), K))


def _aalines(surface, color, closed, points, *args):
    if not isinstance(surface, Canvas):
        return _DRAW["aalines"](surface, color, closed, points, *args)
    return _down(_DRAW["lines"](surface.hi, color, closed, [_pt(p) for p in points], K))


def _make_scaler(name):
    def scaler(surface, size, *args):
        if not isinstance(surface, Canvas):
            return _TF[name](surface, size, *args)
        w, h = max(1, round(size[0])), max(1, round(size[1]))
        return Canvas((w, h), hi=_TF[name](surface.hi, (w * K, h * K)))
    return scaler


def _flip(surface, flip_x, flip_y):
    if not isinstance(surface, Canvas):
        return _TF["flip"](surface, flip_x, flip_y)
    return Canvas(surface.get_size(), hi=_TF["flip"](surface.hi, flip_x, flip_y))


def _rotate(surface, angle):
    if not isinstance(surface, Canvas):
        return _TF["rotate"](surface, angle)
    return Canvas(hi=_TF["rotate"](surface.hi, angle))


def _rotozoom(surface, angle, scale):
    if not isinstance(surface, Canvas):
        return _TF["rotozoom"](surface, angle, scale)
    return Canvas(hi=_TF["rotozoom"](surface.hi, angle, scale))


class _HDMask:
    """Maschera calcolata sull'immagine HD: to_surface restituisce un Canvas."""
    def __init__(self, mask):
        self._mask = mask

    def to_surface(self, *args, **kw):
        return Canvas(hi=self._mask.to_surface(*args, **kw))

    def __getattr__(self, name):
        return getattr(self._mask, name)


def _mask_from_surface(surface, *args):
    if isinstance(surface, Canvas):
        return _HDMask(_MASK_FROM_SURFACE(surface.hi, *args))
    return _MASK_FROM_SURFACE(surface, *args)


def _mouse_get_pos():
    x, y = _MOUSE_GET_POS()
    return x // K, y // K


class HDFont:
    """Font che scrive il testo a K volte la dimensione: lettere nitide sullo schermo grande."""

    def __init__(self, make, size: int):
        self._lo = make(size)
        self._hi = make(size * K)

    def render(self, text, antialias, color, background=None):
        return Canvas(hi=self._hi.render(text, antialias, color, background))

    def __getattr__(self, name):                  # size, get_height, get_linesize, ...
        return getattr(self._lo, name)


def font(make, size: int):
    """make(size) -> pygame.font.Font. HD quando K > 1."""
    return HDFont(make, size) if K > 1 else make(size)


def _install():
    pygame.draw.rect, pygame.draw.circle, pygame.draw.ellipse = _rect, _circle, _ellipse
    pygame.draw.arc, pygame.draw.line, pygame.draw.lines = _arc, _line, _lines
    pygame.draw.polygon, pygame.draw.aaline, pygame.draw.aalines = _polygon, _aaline, _aalines
    pygame.transform.scale = _make_scaler("scale")
    pygame.transform.smoothscale = _make_scaler("smoothscale")
    pygame.transform.flip, pygame.transform.rotate = _flip, _rotate
    pygame.transform.rotozoom = _rotozoom
    pygame.mask.from_surface = _mask_from_surface
    pygame.mouse.get_pos = _mouse_get_pos
