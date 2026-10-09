"""Menu principale: titolo, scelta dello slot di salvataggio, impostazioni.

Stile moderno: sfondo dell'hub sfocato che scorre piano, lucciole, pannelli semitrasparenti,
un solo colore d'accento, selezione che scivola tra le voci, schermate che entrano in
dissolvenza. Testi in Bahnschrift / Segoe UI (presenti su Windows 10 e 11).
"""
import math
import random
import time

import pygame

from game import gfx, save, user_settings as us
from game import settings as s
from game import controls_panel
from game.asset_manager import AssetManager
from game.sound import play

ACCENT   = (255, 184, 92)          # ambra calda, come le torce
WHITE    = (240, 238, 245)
MUTED    = (160, 156, 172)
DIM      = (105, 101, 118)
PANEL    = (18, 16, 26, 170)
PANEL_HI = (40, 34, 56, 200)
LINE     = (255, 255, 255, 34)
DANGER   = (240, 110, 100)

_fonts: dict = {}


def _font(size: int, kind: str = "ui"):
    """kind: "title" (Bahnschrift bold), "head" (Bahnschrift), "ui" (Segoe UI), "bold" (Segoe UI semibold)."""
    key = (size, kind)
    if kind in ("title", "head") and key not in _fonts:   # titoli e voci dei menu: font dipinto
        from game import painted_font
        if painted_font.available():
            _fonts[key] = painted_font.PaintedFont(size, 0.8 if kind == "title" else 0.72)
    if key not in _fonts:
        family, bold = {"title": ("bahnschrift", True), "head": ("bahnschrift", False),
                        "ui": ("segoeui", False), "bold": ("segoeuisemibold", False)}[kind]
        _fonts[key] = gfx.font(lambda sz, f=family, b=bold: pygame.font.SysFont(f, sz, bold=b), size)
    return _fonts[key]


def _spaced(text: str, font, color, spacing: int):
    """Testo con le lettere distanziate (titoletti in maiuscolo)."""
    w = sum(font.size(ch)[0] for ch in text) + spacing * (len(text) - 1)
    surf = gfx.Surface((max(1, w), font.get_height()), pygame.SRCALPHA)
    x = 0
    for ch in text:
        surf.blit(font.render(ch, True, color), (x, 0))
        x += font.size(ch)[0] + spacing
    return surf


def _panel(surface, rect, fill=PANEL, border=LINE, radius=14):
    layer = gfx.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(layer, fill, layer.get_rect(), border_radius=radius)
    pygame.draw.rect(layer, border, layer.get_rect(), 1, border_radius=radius)
    surface.blit(layer, rect.topleft)


def _ease(x: float) -> float:
    return 1 - (1 - max(0.0, min(1.0, x))) ** 3


class MainMenu:
    def __init__(self):
        self.page   = "title"
        self.sel    = 0
        self.slots  = []
        self.note   = ""                  # avviso in basso (es. "al riavvio")
        self._enter = 0.0                 # 0 → 1: animazione d'ingresso della schermata
        self._hl    = None                # posizione della selezione che scivola
        self._quality_at_start = us.get("quality")
        self._bg     = None
        self._shade  = None
        self._flies  = [[random.uniform(0, s.SCREEN_W), random.uniform(0, s.SCREEN_H),
                         random.uniform(6, 18), random.uniform(0, math.tau), random.uniform(1.2, 2.4)]
                        for _ in range(38)]
        self._glow   = None
        self._layer  = None
        self._splash = self.SPLASH                # logo su nero all'avvio (un tasto lo salta)
        self.ingame  = False                      # Impostazioni aperte in partita (dal menu di pausa)
        self._go(self.page)

    # ── Dati ──────────────────────────────────────────────────────────────────

    def _read_slots(self):
        self.slots = []
        for n in range(1, save.SLOTS + 1):
            data = save.read(n)
            self.slots.append(data)

    def _has_any_save(self) -> bool:
        return any(d and d.get("player") for d in self.slots)

    def _latest_slot(self) -> "int | None":
        best, best_t = None, -1
        for i, d in enumerate(self.slots):
            if d and d.get("player") and d.get("saved_at", 0) > best_t:
                best, best_t = i + 1, d.get("saved_at", 0)
        return best

    def _title_items(self) -> list:
        items = [("continue", "Continua")] if self._has_any_save() else []
        return items + [("play", "Gioca"), ("settings", "Impostazioni"), ("quit", "Esci")]

    def _settings_rows(self) -> list:
        return [
            ("fullscreen", "Schermo", "Schermo intero" if us.get("fullscreen") else "Finestra"),
            ("quality", "Qualità grafica", us.QUALITY_NAMES[us.get("quality")]),
            ("brightness", "Luminosità", us.BRIGHTNESS_NAMES[us.get("brightness")]),
            ("music", "Volume musica", us.get("music")),
            ("volume", "Volume effetti", us.get("volume")),
            ("shake", "Scuotimento schermo", "Sì" if us.get("shake") else "No"),
            ("show_fps", "Mostra FPS", "Sì" if us.get("show_fps") else "No"),
            ("back", "Indietro", None),
        ]

    def _go(self, page: str, sel: int = 0):
        self.page, self.sel, self._enter, self._hl = page, sel, 0.0, None
        if page in ("title", "slots"):
            self._read_slots()

    # ── Input ─────────────────────────────────────────────────────────────────

    def handle_key(self, key):
        """Restituisce un'azione per main.py: ("play", slot), "quit", "display", "audio" o None."""
        up    = key in (pygame.K_UP, pygame.K_w)
        down  = key in (pygame.K_DOWN, pygame.K_s)
        left  = key in (pygame.K_LEFT, pygame.K_a)
        right = key in (pygame.K_RIGHT, pygame.K_d)
        ok    = key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER)
        back  = key in (pygame.K_ESCAPE, pygame.K_BACKSPACE)
        if self._splash > 0:                      # il primo tasto salta solo lo splash
            self._end_splash()
            return None

        if self.page == "title":
            items = self._title_items()
            if up or down:
                self.sel = (self.sel + (1 if down else -1)) % len(items)
                play("ui_open", 0.25)
            elif ok:
                what = items[self.sel][0]
                play("ui_open", 0.6)
                if what == "continue":
                    return ("play", self._latest_slot())
                if what == "play":
                    self._go("slots", max(0, (self._latest_slot() or 1) - 1))
                elif what == "settings":
                    self._go("settings")
                else:
                    return "quit"
            elif back:
                self.sel = len(items) - 1
            return None

        if self.page == "slots":
            if left or right or up or down:
                self.sel = (self.sel + (1 if (right or down) else -1)) % save.SLOTS
                play("ui_open", 0.25)
            elif ok:
                play("ui_open", 0.6)
                return ("play", self.sel + 1)
            elif key == pygame.K_DELETE and self.slots[self.sel]:
                self._delete_slot = self.sel
                self._go("delete", 1)
            elif back:
                play("ui_open", 0.4)
                self._go("title", 1 if self._has_any_save() else 0)
            return None

        if self.page == "delete":
            if left or right or up or down:
                self.sel = 1 - self.sel
                play("ui_open", 0.25)
            elif ok and self.sel == 0:
                save.delete(self._delete_slot + 1)
                play("error", 0.5)
                self._go("slots", self._delete_slot)
            elif ok or back:
                self._go("slots", self._delete_slot)
            return None

        # impostazioni
        rows = self._settings_rows()
        if up or down:
            self.sel = (self.sel + (1 if down else -1)) % len(rows)
            play("ui_open", 0.25)
            return None
        what = rows[self.sel][0]
        if back or (ok and what == "back"):
            play("ui_open", 0.4)
            self.note = ""
            if self.ingame:                       # si torna al menu di pausa
                self.ingame = False
                return "close"
            self._go("title", 2 if self._has_any_save() else 1)
            return None
        step = -1 if left else 1
        if not (left or right or ok):
            return None
        play("ui_open", 0.35)
        if what == "fullscreen":
            us.set("fullscreen", not us.get("fullscreen"))
            return "display"
        if what == "quality":
            us.set("quality", (us.get("quality") + step) % len(us.QUALITY_NAMES))
            self.note = ("La qualità grafica cambia al prossimo avvio del gioco."
                         if us.get("quality") != self._quality_at_start else "")
        elif what == "brightness":
            us.set("brightness", (us.get("brightness") + step) % len(us.BRIGHTNESS_NAMES))
        elif what in ("volume", "music"):
            us.set(what, max(0, min(10, us.get(what) + (step if (left or right) else 0))))
            return "audio"
        elif what == "show_fps":
            us.set("show_fps", not us.get("show_fps"))
        elif what == "shake":
            us.set("shake", not us.get("shake"))
        return None

    # ── Disegno ───────────────────────────────────────────────────────────────

    def _prepare(self):
        W, H = s.SCREEN_W, s.SCREEN_H
        path = AssetManager.image_path("bg_hub")
        if path.exists():
            raw = pygame.image.load(str(path)).convert()
            sm  = gfx._TF["smoothscale"]
            w, h = raw.get_size()
            blur = raw
            for f in (8, 4):                                   # sfocatura: giù e su due volte
                blur = sm(sm(blur, (max(1, w // f), max(1, h // f))), (w, h))
            self._bg = gfx.fit(blur, (round(W * 1.08), round(H * 1.08)))
        shade = gfx.Surface((W, H), pygame.SRCALPHA)           # più scuro a sinistra e in basso
        for x in range(0, W, 4):
            a = round(215 - 120 * (x / W) ** 0.8)
            pygame.draw.rect(shade, (10, 8, 16, a), (x, 0, 4, H))
        bottom = gfx.Surface((W, 220), pygame.SRCALPHA)       # e in basso (si somma, non sostituisce)
        for y in range(0, 220, 4):
            pygame.draw.rect(bottom, (6, 5, 10, round(150 * (y / 220) ** 2)), (0, y, W, 4))
        shade.blit(bottom, (0, H - 220))
        self._shade = shade
        # alone delle lucciole: colori già sfumati verso il nero, si somma allo sfondo (ADD)
        glow = gfx.Surface((20, 20))
        glow.fill((0, 0, 0))
        for r in range(10, 0, -1):
            k = (1 - r / 10) ** 2 * 0.55
            pygame.draw.circle(glow, (round(255 * k), round(190 * k), round(110 * k)), (10, 10), r)
        self._glow  = glow
        self._layer = gfx.Surface((W, H), pygame.SRCALPHA)

    SPLASH = 1.0                                   # > 0: splash attivo (resta finché non premi un tasto)

    def _end_splash(self):
        self._splash, self._enter, self._hl = 0.0, 0.0, None

    def _draw_splash(self, surface):
        """Logo fermo su nero e, sotto, "Premi un tasto per continuare" che respira."""
        surface.fill((0, 0, 0))
        e = getattr(self, "_splash_t", 0.0)                 # tempo passato
        logo = self._logo()
        if logo is not None:
            img = logo.copy()
            img.set_alpha(round(255 * min(1.0, e / 0.8)))   # entra piano, poi resta fermo
            surface.blit(img, img.get_rect(center=(s.SCREEN_W // 2, s.SCREEN_H // 2 - 20)))
        if e > 1.0:
            from game.input import InputManager
            text = "Premi un tasto per continuare"
            if InputManager.get().using_controller:
                text = "Premi un pulsante per continuare"
            pulse = 0.5 + 0.5 * math.sin((e - 1.0) * 2.6 - math.pi / 2)
            prompt = _spaced(text.upper(), _font(15, "bold"), (230, 214, 186), 4)
            prompt.set_alpha(round(255 * min(1.0, (e - 1.0) / 0.5) * (0.35 + 0.65 * pulse)))
            surface.blit(prompt, prompt.get_rect(center=(s.SCREEN_W // 2, s.SCREEN_H - 120)))

    def update(self, dt: float):
        if self._splash > 0:
            self._splash_t = getattr(self, "_splash_t", 0.0) + dt
            return
        self._enter = min(1.0, self._enter + dt / 0.35)
        for f in self._flies:                                   # lucciole che salgono piano
            f[1] -= f[2] * dt
            f[0] += math.sin(f[3] + f[1] * 0.02) * 8 * dt
            if f[1] < -20:
                f[0], f[1] = random.uniform(0, s.SCREEN_W), s.SCREEN_H + 20

    def draw_background(self, surface):
        if self._shade is None:
            self._prepare()
        t = pygame.time.get_ticks() / 1000.0
        if self._bg is not None:
            ox = round((self._bg.get_width() - s.SCREEN_W) / 2 * (1 + math.sin(t * 0.05)))
            oy = round((self._bg.get_height() - s.SCREEN_H) / 2 * (1 + math.cos(t * 0.04)))
            surface.blit(self._bg, (-ox, -oy))
        else:
            surface.fill((20, 18, 28))
        surface.blit(self._shade, (0, 0))
        for x, y, _, ph, sz in self._flies:
            a = 0.5 + 0.5 * math.sin(t * sz + ph)
            if a > 0.25:
                self._glow.set_alpha(None)
                surface.blit(self._glow, (round(x) - 10, round(y) - 10), special_flags=pygame.BLEND_RGB_ADD)
                pygame.draw.circle(surface, (255, 236, 180), (round(x), round(y)), 1)

    def draw_ingame(self, surface, dt: float = 0.016):
        """Impostazioni sopra la partita (velo scuro al posto dello sfondo del menu)."""
        veil = gfx.Surface((s.SCREEN_W, s.SCREEN_H), pygame.SRCALPHA)
        veil.fill((10, 8, 16, 236))
        surface.blit(veil, (0, 0))
        layer = self._layer if self._layer is not None else gfx.Surface((s.SCREEN_W, s.SCREEN_H), pygame.SRCALPHA)
        self._layer = layer
        layer.fill((0, 0, 0, 0))
        self._draw_settings(layer, dt)
        k = _ease(self._enter)
        layer.set_alpha(round(255 * k))
        surface.blit(layer, (round(18 * (1 - k)), 0))
        self._draw_hints(surface)

    def draw(self, surface, dt: float = 0.016):
        if self._splash > 0:
            self._draw_splash(surface)
            return
        self.draw_background(surface)
        layer = self._layer
        layer.fill((0, 0, 0, 0))
        {"title": self._draw_title, "slots": self._draw_slots, "delete": self._draw_slots,
         "settings": self._draw_settings}[self.page](layer, dt)
        k = _ease(self._enter)
        layer.set_alpha(round(255 * k))
        surface.blit(layer, (round(18 * (1 - k)), 0))
        if self.page == "delete":
            self._draw_delete(surface)
        self._draw_hints(surface)

    def _slide(self, target: float, dt: float) -> float:
        """Selezione che scivola verso la voce scelta."""
        self._hl = target if self._hl is None else self._hl + (target - self._hl) * min(1.0, dt * 16)
        return self._hl

    # Titolo
    LOGO_W = 700                                   # larghezza del logo sul menu (logica)
    _LOGO_LIGHTS = [(75, 270, 46), (1263, 406, 70)]   # lanterna e zampa, in pixel dell'immagine

    def _logo(self):
        if not hasattr(self, "_logo_img"):
            path = AssetManager.image_path("logo")
            self._logo_img = None
            if path.exists():
                img = pygame.image.load(str(path)).convert_alpha()
                self._logo_scale = self.LOGO_W / img.get_width()
                self._logo_img = gfx.fit(img, (self.LOGO_W, round(img.get_height() * self._logo_scale)))
        return self._logo_img

    def _draw_title(self, surface, dt):
        x = 112
        logo = self._logo()
        t = pygame.time.get_ticks() / 1000.0
        if logo is not None:
            lx, ly = x - 26, 70
            surface.blit(logo, (lx, ly))
            for i, (gx, gy, r) in enumerate(self._LOGO_LIGHTS):     # luce che respira
                k  = 0.55 + 0.45 * math.sin(t * (2.1 + i * 0.7) + i)
                rr = round(r * self._logo_scale * (1.6 + 0.3 * k))
                glow = self._glow
                big = pygame.transform.smoothscale(glow, (rr * 2, rr * 2))
                big.set_alpha(round(120 * k))
                surface.blit(big, (lx + round(gx * self._logo_scale) - rr, ly + round(gy * self._logo_scale) - rr),
                             special_flags=pygame.BLEND_RGB_ADD)
        else:
            surface.blit(_font(92, "title").render("KITTENBOUND", True, WHITE), (x, 172))

        items = self._title_items()
        self.sel %= len(items)
        y0, step = 350, 58
        hy = self._slide(y0 + self.sel * step, dt)
        pill = pygame.Rect(x - 14, round(hy) - 6, 330, 50)
        _panel(surface, pill, fill=(255, 184, 92, 34), border=(255, 184, 92, 90), radius=10)
        pygame.draw.rect(surface, ACCENT, (pill.x, pill.y + 10, 4, pill.h - 20), border_radius=2)
        f = _font(30, "head")
        for i, (_, label) in enumerate(items):
            col = WHITE if i == self.sel else MUTED
            surface.blit(f.render(label, True, col), (x + 8, y0 + i * step))
        if items[self.sel][0] == "continue":
            n = self._latest_slot()
            info = self._slot_line(self.slots[n - 1]) if n else ""
            surface.blit(_font(16).render(f"Slot {n}  ·  {info}", True, MUTED), (x + 8, y0 + len(items) * step + 10))

    # Slot
    @staticmethod
    def _slot_line(d) -> str:
        sess = d.get("session") or {}
        biome = s.BIOMES[min(sess.get("biome", 1), len(s.BIOMES)) - 1]["name"]
        where = f"{biome} · Piano {sess.get('floor', 1)}" if sess.get("location") == "dungeon" else f"Hub · {biome}"
        return where

    def _draw_slots(self, surface, dt):
        surface.blit(_spaced("SALVATAGGI", _font(15, "bold"), ACCENT, 5), (112, 96))
        surface.blit(_font(44, "title").render("Scegli una partita", True, WHITE), (110, 118))
        cw, ch, gap = 330, 300, 28
        x0 = (s.SCREEN_W - (3 * cw + 2 * gap)) // 2
        y0 = 230
        t  = pygame.time.get_ticks() / 1000.0
        current = self._delete_slot if self.page == "delete" else self.sel   # nella conferma resta lo slot scelto
        for i in range(save.SLOTS):
            d    = self.slots[i] if i < len(self.slots) else None
            sel  = i == current
            lift = 8 if sel else 0
            rect = pygame.Rect(x0 + i * (cw + gap), y0 - lift, cw, ch)
            _panel(surface, rect, fill=PANEL_HI if sel else PANEL,
                   border=(255, 184, 92, 200) if sel else LINE, radius=16)
            surface.blit(_spaced(f"SLOT {i + 1}", _font(13, "bold"), ACCENT if sel else DIM, 4), (rect.x + 24, rect.y + 22))
            if not d or not d.get("player"):
                cx, cy = rect.centerx, rect.y + 130
                pulse = 1 + (0.06 * math.sin(t * 3) if sel else 0)
                r = round(30 * pulse)
                pygame.draw.circle(surface, ACCENT if sel else DIM, (cx, cy), r, 2)
                pygame.draw.rect(surface, ACCENT if sel else DIM, (cx - 12, cy - 1, 24, 3))
                pygame.draw.rect(surface, ACCENT if sel else DIM, (cx - 1, cy - 12, 3, 24))
                lbl = _font(24, "head").render("Nuova partita", True, WHITE if sel else MUTED)
                surface.blit(lbl, lbl.get_rect(centerx=cx, top=cy + 46))
                bag = ((d or {}).get("meta") or {}).get("lost_bag")
                if bag:
                    chip = _font(14).render(f"Sacca a terra: {bag['gold']} oro (piano {bag['floor']})", True, ACCENT)
                    surface.blit(chip, chip.get_rect(centerx=cx, top=cy + 86))
                continue
            sess, p = d.get("session") or {}, d["player"]
            biome = s.BIOMES[min(sess.get("biome", 1), len(s.BIOMES)) - 1]["name"]
            in_dg = sess.get("location") == "dungeon"
            surface.blit(_font(40, "title").render(biome, True, WHITE), (rect.x + 22, rect.y + 48))
            sub = f"Piano {sess.get('floor', 1)} · nel dungeon" if in_dg else "All'hub"
            surface.blit(_font(18).render(sub, True, MUTED), (rect.x + 24, rect.y + 100))
            pygame.draw.line(surface, (255, 255, 255, 40), (rect.x + 24, rect.y + 140), (rect.right - 24, rect.y + 140))
            stats = [("Livello", str(p.get("level", 1))), ("Oro", str(p.get("gold", 0))),
                     ("Pozioni", str(p.get("potions", 0)))]
            for k, (name, val) in enumerate(stats):
                sx = rect.x + 24 + k * 100
                surface.blit(_font(28, "head").render(val, True, ACCENT if name == "Oro" else WHITE), (sx, rect.y + 154))
                surface.blit(_font(14).render(name, True, DIM), (sx, rect.y + 190))
            hp = f"Vita {round(p.get('hp', 0))}/{p.get('hp_max', 0)}"
            surface.blit(_font(15).render(hp, True, MUTED), (rect.x + 24, rect.y + 222))
            when = d.get("saved_at")
            if when:
                stamp = time.strftime("%d/%m/%Y  %H:%M", time.localtime(when))
                surface.blit(_font(14).render(stamp, True, DIM), (rect.x + 24, rect.bottom - 34))

    def _draw_delete(self, surface):
        veil = gfx.Surface((s.SCREEN_W, s.SCREEN_H), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 150))
        surface.blit(veil, (0, 0))
        rect = pygame.Rect(0, 0, 520, 230)
        rect.center = (s.SCREEN_W // 2, s.SCREEN_H // 2)
        _panel(surface, rect, fill=(24, 20, 34, 245), border=(240, 110, 100, 150), radius=16)
        surface.blit(_font(30, "title").render(f"Eliminare lo slot {self._delete_slot + 1}?", True, WHITE), (rect.x + 32, rect.y + 30))
        surface.blit(_font(17).render("La partita andrà persa per sempre.", True, MUTED), (rect.x + 34, rect.y + 80))
        for i, label in enumerate(("Elimina", "Annulla")):
            b = pygame.Rect(rect.x + 32 + i * 236, rect.bottom - 78, 220, 50)
            sel = i == self.sel
            col = DANGER if i == 0 else ACCENT
            _panel(surface, b, fill=(*col, 60) if sel else (255, 255, 255, 10),
                   border=(*col, 220) if sel else LINE, radius=10)
            lbl = _font(22, "head").render(label, True, WHITE if sel else MUTED)
            surface.blit(lbl, lbl.get_rect(center=b.center))

    # Impostazioni
    def _draw_settings(self, surface, dt):
        surface.blit(_spaced("OPZIONI", _font(15, "bold"), ACCENT, 5), (112, 96))
        surface.blit(_font(44, "title").render("Impostazioni", True, WHITE), (110, 118))
        rows = self._settings_rows()
        step = 58 if len(rows) <= 7 else 52     # con tante righe si stringono un po'
        box = pygame.Rect(96, 196, 640, 24 + step * len(rows))
        _panel(surface, box, radius=16)
        y0 = box.y + 22                         # y0 = alto della riga; il centro è y + 15
        hy = self._slide(y0 + self.sel * step, dt)
        pill = pygame.Rect(box.x + 12, round(hy) - 10, box.w - 24, 50)
        _panel(surface, pill, fill=(255, 184, 92, 30), border=(255, 184, 92, 80), radius=10)
        pygame.draw.rect(surface, ACCENT, (pill.x, pill.y + 10, 4, pill.h - 20), border_radius=2)
        for i, (key, label, value) in enumerate(rows):
            y = y0 + i * step
            sel = i == self.sel
            lbl = _font(22, "head").render(label, True, WHITE if sel else MUTED)
            surface.blit(lbl, lbl.get_rect(x=box.x + 34, centery=y + 15))
            if value is None:
                continue
            right = box.right - 40
            if key in ("volume", "music"):                        # barra a tacche
                for k in range(10):
                    on = k < value
                    pygame.draw.rect(surface, ACCENT if on else (255, 255, 255, 40),
                                     (right - 220 + k * 22, y + 6, 16, 18), border_radius=3)
                txt = _font(18, "bold").render(f"{value * 10}%", True, WHITE if sel else MUTED)
                surface.blit(txt, txt.get_rect(right=right - 232, centery=y + 15))
            else:
                txt = _font(20, "bold").render(str(value), True, WHITE if sel else MUTED)
                r = txt.get_rect(right=right - 18, centery=y + 15)
                surface.blit(txt, r)
                if sel:                                           # frecce per cambiare valore
                    for dx, pts in ((-1, [(0, 0), (-7, 6), (0, 12)]), (1, [(0, 0), (7, 6), (0, 12)])):
                        ax = r.x - 16 if dx < 0 else r.right + 14
                        pygame.draw.polygon(surface, ACCENT, [(ax + px, y + 9 + py) for px, py in pts])
        if self.note:
            surface.blit(_font(16).render(self.note, True, ACCENT), (box.x + 4, box.bottom + 16))

    # Suggerimenti in basso
    def _draw_hints(self, surface):
        hints = [("confirm", "Seleziona"), ("back", "Indietro")]
        if self.page == "slots" and self.sel < len(self.slots) and self.slots[self.sel]:
            hints.append(("delete", "Elimina"))
        if self.page == "settings":
            hints.insert(1, ("change", "Cambia"))
        x, y = 112, s.SCREEN_H - 46
        f = _font(16)
        for action, label in hints:
            w = controls_panel.draw_button(surface, action, x + 14, y + 10)
            x += max(w, 28) + 8
            surface.blit(f.render(label, True, MUTED), (x, y))
            x += f.size(label)[0] + 30
        ver = _font(14).render(s.VERSION, True, DIM)
        surface.blit(ver, ver.get_rect(right=s.SCREEN_W - 28, bottom=s.SCREEN_H - 24))
