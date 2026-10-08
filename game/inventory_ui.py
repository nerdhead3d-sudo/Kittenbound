"""Menu dell'equipaggiamento, che è anche la pausa (ESC / Options / I / Create / touchpad).

A sinistra l'illustrazione del gatto, a destra: i 3 oggetti, le 2 magie e la partita
(menu principale, esci). Su un oggetto o una magia, conferma passa al successivo.
"""
import math

import pygame

from game import gfx, equipment as eq, spells
from game import settings as s
from game import controls_panel
from game.asset_manager import AssetManager
from game.input import InputManager
from game.menu import _font, _spaced, _panel, ACCENT, WHITE, MUTED, DIM
from game.sound import play

ROWS   = [("slot", "claws"), ("slot", "collar"), ("slot", "amulet"), ("spell", 0), ("spell", 1),
          ("game", "menu"), ("game", "quit")]
GAME_LABELS = {"menu": "Menu principale", "quit": "Esci dal gioco"}
LIST_X = 700
LIST_W = 500
ROW_H  = 60
GAME_H = 40


class InventoryUI:
    def __init__(self):
        self.sel  = 0
        self._t   = 0.0
        self._hl  = None
        self._cat = None
        self._bg  = None
        self.msg, self.msg_t = "", 0.0

    def open(self):
        self.sel, self._t, self._hl, self.msg_t = 0, 0.0, None, 0.0
        play("page", 0.6)

    def update(self, dt):
        self._t += dt
        self.msg_t = max(0.0, self.msg_t - dt)

    # ── Input ─────────────────────────────────────────────────────────────────

    def handle_key(self, key, player) -> "str | None":
        """None, oppure "close" (riprendi), "menu" (menu principale) o "quit" (esci dal gioco)."""
        if key in (pygame.K_ESCAPE, pygame.K_i, pygame.K_TAB):
            play("page", 0.5)
            return "close"
        if ROWS[self.sel][0] == "game" and key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
            play("ui_open", 0.6)
            return ROWS[self.sel][1]
        if key in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s):
            self.sel = (self.sel + (1 if key in (pygame.K_DOWN, pygame.K_s) else -1)) % len(ROWS)
            play("ui_open", 0.2)
        elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e, pygame.K_RIGHT, pygame.K_d,
                     pygame.K_LEFT, pygame.K_a):
            step = -1 if key in (pygame.K_LEFT, pygame.K_a) else 1
            kind, val = ROWS[self.sel]
            if kind == "game":
                return None
            changed = self._cycle_item(player, val, step) if kind == "slot" else self._cycle_spell(player, val, step)
            if changed:
                play("buy" if kind == "slot" else "spell_mark", 0.6)
            else:
                self.msg, self.msg_t = "Nient'altro da scegliere", 1.2
                play("error", 0.35)
        return None

    @staticmethod
    def _options(player, slot) -> list:
        cur = player.equipment.get(slot)
        return ([cur] if cur else []) + [i for i in player.backpack if eq.ITEMS[i].slot == slot]

    def _cycle_item(self, player, slot, step) -> bool:
        opts = self._options(player, slot)
        if len(opts) < 2:
            return False
        eq.equip(player, opts[step % len(opts)])
        return True

    @staticmethod
    def _cycle_spell(player, i, step) -> bool:
        owned = [sp for sp in spells.ORDER if sp in player.spells_owned]
        cur = player.spell_slots[i]
        if len(owned) < 2 and cur in owned:
            return False
        nxt = owned[((owned.index(cur) if cur in owned else -1) + step) % len(owned)]
        other = 1 - i
        if player.spell_slots[other] == nxt:          # era nell'altro slot: scambio
            player.spell_slots[other] = cur
        player.spell_slots[i] = nxt
        return True

    # ── Disegno ───────────────────────────────────────────────────────────────

    def _prepare(self):
        W, H = s.SCREEN_W, s.SCREEN_H
        bg = gfx.Surface((W, H), pygame.SRCALPHA)
        bg.fill((10, 8, 16, 255))
        glow = gfx.Surface((W, H), pygame.SRCALPHA)         # alone caldo dietro il gatto
        for r in range(360, 0, -12):
            a = round(46 * (1 - r / 360) ** 1.6)
            pygame.draw.circle(glow, (255, 170, 80, a), (330, 380), r)
        bg.blit(glow, (0, 0))
        self._bg = bg
        path = AssetManager.image_path("cat_art")
        self._cat = False
        if path.exists():
            img = pygame.image.load(str(path)).convert_alpha()
            w = 560
            self._cat = gfx.fit(img, (w, round(img.get_height() * w / img.get_width())))

    def draw(self, surface, player):
        if self._bg is None:
            self._prepare()
        t = self._t
        surface.blit(self._bg, (0, 0))

        if self._cat:                                         # il gatto, che respira piano
            bob = round(4 * math.sin(t * 1.8))
            shadow = gfx.Surface((460, 34), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 120), shadow.get_rect())
            surface.blit(shadow, (100, 600))
            surface.blit(self._cat, self._cat.get_rect(midbottom=(330, 618 + bob)))

        surface.blit(_spaced("PAUSA", _font(13, "bold"), ACCENT, 5), (LIST_X, 38))
        surface.blit(_font(40, "title").render("Equipaggiamento", True, WHITE), (LIST_X, 56))

        y_items, y_spells, y_game = 150, 376, 538
        surface.blit(_spaced("OGGETTI", _font(13, "bold"), ACCENT, 4), (LIST_X, y_items - 24))
        surface.blit(_spaced("MAGIE", _font(13, "bold"), ACCENT, 4), (LIST_X, y_spells - 24))
        surface.blit(_spaced("PARTITA", _font(13, "bold"), ACCENT, 4), (LIST_X, y_game - 24))
        ys = ([y_items + i * (ROW_H + 6) for i in range(3)] + [y_spells + i * (ROW_H + 6) for i in range(2)]
              + [y_game + i * (GAME_H + 6) for i in range(2)])

        target = ys[self.sel]
        h = GAME_H if ROWS[self.sel][0] == "game" else ROW_H
        self._hl = target if self._hl is None else self._hl + (target - self._hl) * 0.25
        pill = pygame.Rect(LIST_X - 12, round(self._hl), LIST_W, h)
        _panel(surface, pill, fill=(255, 184, 92, 30), border=(255, 184, 92, 110), radius=12)
        pygame.draw.rect(surface, ACCENT, (pill.x, pill.y + 10, 4, h - 20), border_radius=2)

        self._detail = ""
        for i, (kind, val) in enumerate(ROWS):
            sel = i == self.sel
            if kind == "slot":
                self._draw_item_row(surface, player, val, ys[i], sel)
            elif kind == "spell":
                self._draw_spell_row(surface, player, val, ys[i], sel, t)
            else:
                lbl = _font(20, "head").render(GAME_LABELS[val], True, WHITE if sel else (200, 195, 210))
                surface.blit(lbl, lbl.get_rect(x=LIST_X + 6, centery=ys[i] + GAME_H // 2))

        if self._detail:                                      # sotto il titolo: cosa fa la voce scelta
            surface.blit(_font(15).render(self._detail, True, MUTED), (LIST_X, 104))
        x, y = LIST_X, s.SCREEN_H - 44
        for action, label in (("confirm", "Conferma"), ("back", "Riprendi")):
            w = controls_panel.draw_button(surface, action, x + 14, y + 10)
            x += max(w, 28) + 8
            surface.blit(_font(16).render(label, True, MUTED), (x, y))
            x += _font(16).size(label)[0] + 30
        if self.msg_t > 0:
            m = _font(16).render(self.msg, True, MUTED)
            m.set_alpha(round(255 * min(1.0, self.msg_t / 0.3)))
            surface.blit(m, (LIST_X, s.SCREEN_H - 84))

    def _count_badge(self, surface, n, y, sel):
        """Quante scelte ci sono su questa riga (es. 2/3): solo se più di una."""
        if n[1] < 2:
            return
        txt = _font(15, "bold").render(f"{n[0]}/{n[1]}", True, ACCENT if sel else DIM)
        surface.blit(txt, txt.get_rect(right=LIST_X + LIST_W - 30, centery=y + ROW_H // 2))

    def _draw_item_row(self, surface, player, slot, y, sel):
        item_id = player.equipment.get(slot)
        tile = pygame.Rect(LIST_X + 4, y + 9, 48, 48)
        col = eq.RARITY_COLORS[eq.ITEMS[item_id].rarity] if item_id else (70, 66, 86)
        _panel(surface, tile, fill=(24, 20, 34, 230), border=(*col, 220 if item_id else 90), radius=10)
        if item_id:
            eq.draw_icon(surface, item_id, tile.center, 38)
        surface.blit(_font(13, "bold").render(eq.SLOT_NAMES[slot].upper(), True, DIM), (LIST_X + 68, y + 10))
        name = eq.ITEMS[item_id].name if item_id else "—"
        col = (WHITE if sel else (215, 210, 225)) if item_id else DIM
        surface.blit(_font(20, "head").render(name, True, col), (LIST_X + 68, y + 28))
        self._count_badge(surface, (1, len(self._options(player, slot))), y, sel)
        if sel and item_id:                                   # effetto: in basso, solo per la riga scelta
            self._detail = eq.ITEMS[item_id].desc

    def _draw_spell_row(self, surface, player, i, y, sel, t):
        sid = player.spell_slots[i]
        sp  = spells.SPELLS.get(sid) if sid else None
        tile = pygame.Rect(LIST_X + 4, y + 9, 48, 48)
        _panel(surface, tile, fill=(24, 20, 34, 230),
               border=(*(sp.color if sp else (70, 66, 86)), 200 if sp else 90), radius=10)
        art = eq.icon(f"spell_{sid}", 46) if sp else None
        if art is not None:
            surface.blit(art, art.get_rect(center=tile.center))
        elif sp:
            glow = 0.5 + 0.5 * math.sin(t * 3 + i)
            pygame.draw.circle(surface, sp.color, tile.center, 11)
            pygame.draw.circle(surface, (255, 255, 255), (tile.centerx - 3, tile.centery - 3), 3)
            pygame.draw.circle(surface, sp.color, tile.center, 15 + round(2 * glow), 1)
        key = InputManager.get().label("F" if i == 0 else "R", "{Y}" if i == 0 else "{B}")
        surface.blit(AssetManager.get().ui_font(13, bold=True).render(key, True, DIM), (LIST_X + 68, y + 9))
        col = (WHITE if sel else (215, 210, 225)) if sp else DIM
        surface.blit(_font(20, "head").render(sp.name if sp else "—", True, col), (LIST_X + 68, y + 28))
        owned = [x for x in spells.ORDER if x in player.spells_owned]
        self._count_badge(surface, ((owned.index(sid) + 1) if sid in owned else 0, len(owned)), y, sel)
        if sel and sp:
            self._detail = f"{sp.desc}  ·  {sp.cost} energia"
