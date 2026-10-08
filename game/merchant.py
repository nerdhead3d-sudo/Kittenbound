"""Mercante nascosto: in alcuni piani si nasconde in una stanza (di solito un vicolo cieco) e
esce dall'ombra solo quando la stanza è liberata. Vende 3 cose scelte a caso, ognuna una volta.

Non compare sulla mappa finché non lo trovi. Il modello è provvisorio: l'Alchimista dell'hub
scurito e con la lanterna, finché non c'è un modello suo.
"""
import math
import random

import pygame

from game import settings as s, gfx
from game.asset_manager import AssetManager
from game.input import InputManager
from game.sound import play
from game.vendor_ui import upgrade_cost

# Potenziamento raro: il doppio del normale, a poco più del prezzo dell'Alchimista
_RARE = {
    "hp_max":     ("Cuore di Topo",   f"+{2 * s.UPGRADE_HP_MAX_AMOUNT} HP max",     s.UPGRADE_HP_MAX_COST),
    "energy_max": ("Coda Elettrica",  f"+{2 * s.UPGRADE_ENERGY_MAX_AMOUNT} EN max", s.UPGRADE_ENERGY_MAX_COST),
    "melee_dmg":  ("Artigli Affilati", f"+{2 * s.UPGRADE_MELEE_DMG_AMOUNT} danno melee", s.UPGRADE_MELEE_DMG_COST),
    "hp_regen":   ("Erba Gattaia",    f"+{2 * s.UPGRADE_HP_REGEN_AMOUNT:g} HP/s",   s.UPGRADE_HP_REGEN_COST),
}
OFFERS = ("potion", "elixir", "rare", "map", "audacia")


class Merchant:
    def __init__(self, x: float, y: float, rng: random.Random):
        self.pos      = pygame.math.Vector2(x, y)
        self.offers   = rng.sample(OFFERS, s.MERCHANT_OFFERS)
        self.rare     = rng.choice(list(_RARE))
        self.sold     = set()
        self.revealed = False
        self.reveal_t = 0.0          # fumo quando esce dall'ombra
        self._angle   = 90.0
        self._last_t  = None
        self._frames  = None

    # ── Offerte ───────────────────────────────────────────────────────────────

    def offer(self, kind: str, player) -> tuple:
        """(nome, descrizione, prezzo) di un'offerta."""
        if kind == "potion":
            return "Pozione", f"+1 pozione ({s.POTION_HEAL} HP)", s.MERCHANT_POTION_PRICE
        if kind == "elixir":
            return "Elisir", "Cura tutti gli HP e l'energia", s.MERCHANT_ELIXIR_PRICE
        if kind == "map":
            return "Mappa del piano", "Mostra tutte le stanze sulla mappa", s.MERCHANT_MAP_PRICE
        if kind == "audacia":
            return "Fiamma Audace", f"+{s.MERCHANT_AUDACIA} Audacia", s.MERCHANT_AUDACIA_PRICE
        name, desc, base = _RARE[self.rare]
        return name, f"{desc} (raro)", round(upgrade_cost(player, self.rare, base) * s.MERCHANT_RARE_MULT)

    def buy(self, kind: str, player, dungeon) -> str | None:
        """Compra; restituisce il messaggio d'errore o None se è andata."""
        if kind in self.sold:
            return "Già venduto"
        _, _, price = self.offer(kind, player)
        if kind == "potion" and player.potions >= s.POTION_MAX:
            return "Borsa piena!"
        if player.gold < price:
            return "Oro insufficiente!"
        player.gold -= price
        if kind == "potion":
            player.potions += 1
        elif kind == "elixir":
            player.hp, player.energy = float(player.hp_max), float(player.energy_max)
        elif kind == "map":
            for room in dungeon.grid.values():
                room.visited = True
        elif kind == "audacia":
            player.add_audacia(s.MERCHANT_AUDACIA)
        else:
            amount = {"hp_max": s.UPGRADE_HP_MAX_AMOUNT, "energy_max": s.UPGRADE_ENERGY_MAX_AMOUNT,
                      "melee_dmg": s.UPGRADE_MELEE_DMG_AMOUNT, "hp_regen": s.UPGRADE_HP_REGEN_AMOUNT}[self.rare]
            attr = {"hp_max": "hp_max", "energy_max": "energy_max",
                    "melee_dmg": "melee_damage_bonus", "hp_regen": "hp_regen_bonus"}[self.rare]
            setattr(player, attr, getattr(player, attr) + 2 * amount)
            if self.rare == "hp_max":
                player.hp += 2 * amount
            elif self.rare == "energy_max":
                player.energy += 2 * amount
        self.sold.add(kind)
        return None

    # ── Mondo ─────────────────────────────────────────────────────────────────

    def near(self, player) -> bool:
        return self.revealed and (player.pos - self.pos).length() < s.MERCHANT_RANGE

    def reveal(self):
        if not self.revealed:
            self.revealed = True
            self.reveal_t = 0.6
            play("shadow", 0.6)

    def update(self, dt: float):
        self.reveal_t = max(0.0, self.reveal_t - dt)

    def _sprites(self):
        """Cicli da fermo dell'Alchimista, scuriti e tinti di viola (provvisorio)."""
        if self._frames is None:
            loops = AssetManager.get().npc_loops("npc_alchemist") or []
            dark = []
            for frames in loops:
                tinted = []
                for f in frames:
                    g = f.copy()
                    g.fill((105, 92, 135, 255), special_flags=pygame.BLEND_RGBA_MULT)
                    tinted.append(g)
                dark.append(tinted)
            feet = AssetManager.sprite_meta("npc_alchemist").get("ground_px", 30)
            self._frames = (dark, round(feet))
        return self._frames

    def draw(self, surface, camera_offset, player=None):
        if not self.revealed:
            return
        t  = pygame.time.get_ticks() / 1000.0
        cx = round(self.pos.x) - camera_offset[0]
        cy = round(self.pos.y) - camera_offset[1]
        loops, feet = self._sprites()

        # tappeto con la merce e il sacco di monete
        pygame.draw.ellipse(surface, (0, 0, 0, 90), (cx - 34, cy - 8, 68, 18))
        pygame.draw.rect(surface, (78, 34, 52), (cx + 14, cy - 2, 40, 16), border_radius=3)
        pygame.draw.rect(surface, (150, 110, 60), (cx + 14, cy - 2, 40, 16), 1, border_radius=3)
        for k, col in enumerate(((200, 60, 70), (80, 160, 230), (240, 200, 70))):
            pygame.draw.circle(surface, col, (cx + 22 + k * 12, cy + 5), 4)
            pygame.draw.circle(surface, (255, 255, 255), (cx + 21 + k * 12, cy + 3), 1)

        if loops:
            target = 90.0                                         # si gira piano verso il gatto
            if player is not None:
                to_p = player.pos - self.pos
                if 0 < to_p.length() < s.NPC_LOOK_RANGE:
                    target = math.degrees(math.atan2(to_p.y, to_p.x))
            dt = 0.0 if self._last_t is None else min(0.1, max(0.0, t - self._last_t))
            self._last_t = t
            diff = (target - self._angle + 180) % 360 - 180
            step = s.NPC_TURN_SPEED * dt
            self._angle = (target if abs(diff) <= step else self._angle + math.copysign(step, diff)) % 360
            frames = loops[round(self._angle / (360 / len(loops))) % len(loops)]
            frame  = frames[int(t * 8) % len(frames)]
            surface.blit(frame, frame.get_rect(center=(cx, cy - feet)))
        else:
            pygame.draw.ellipse(surface, (60, 44, 80), (cx - 14, cy - 50, 28, 50))

        # lanterna che ondeggia
        lx, ly = cx - 26, cy - 34 + round(2 * math.sin(t * 2.2))
        pygame.draw.line(surface, (70, 60, 50), (lx, ly - 10), (lx, ly - 4), 2)
        pygame.draw.rect(surface, (60, 50, 40), (lx - 5, ly - 4, 10, 12), border_radius=2)
        pygame.draw.rect(surface, (255, 200, 110), (lx - 3, ly - 2, 6, 8), border_radius=2)

        if self.reveal_t > 0:                                     # sbuffo d'ombra all'arrivo
            k = 1 - self.reveal_t / 0.6
            for i in range(10):
                a = i / 10 * math.tau
                r = 10 + 34 * k
                pygame.draw.circle(surface, (110, 80, 150), (cx + round(math.cos(a) * r), cy - 24 + round(math.sin(a) * r * 0.6)),
                                   max(1, round(7 * (1 - k))))

        if player is not None and self.near(player):              # tasto per parlarci, sopra la testa
            from game import controls_panel
            controls_panel.draw_button(surface, "interact", cx, cy - 2 * feet - 18)

    def light(self) -> tuple:
        return round(self.pos.x) - 26, round(self.pos.y) - 34, s.MERCHANT_LIGHT_RADIUS


class MerchantUI:
    """Il negozio del mercante: 3 offerte, frecce per scegliere, INVIO / ✕ per comprare."""

    def __init__(self):
        am = AssetManager.get()
        self._font_title = am.font(24, bold=True)
        self._font       = am.font(18)
        self._font_small = am.font(15)
        self.merchant    = None
        self._sel        = 0
        self._msg        = ""
        self._msg_timer  = 0.0
        self._msg_err    = False

    def open(self, merchant: Merchant):
        self.merchant, self._sel, self._msg_timer = merchant, 0, 0.0

    def update(self, dt: float):
        self._msg_timer = max(0.0, self._msg_timer - dt)

    def _say(self, text: str, error: bool):
        self._msg, self._msg_timer, self._msg_err = text, 1.5, error
        play("error" if error else "buy", 0.6 if error else 0.8)

    def handle_key(self, key, player, dungeon) -> bool:
        """True se il negozio va chiuso."""
        if key in (pygame.K_e, pygame.K_ESCAPE):
            return True
        n = len(self.merchant.offers)
        if key in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s):
            self._sel = (self._sel + (-1 if key in (pygame.K_UP, pygame.K_w) else 1)) % n
            play("ui_open", 0.3)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            kind = self.merchant.offers[self._sel]
            name = self.merchant.offer(kind, player)[0]
            err  = self.merchant.buy(kind, player, dungeon)
            self._say(err or f"{name}: affare fatto!", err is not None)
        return False

    def draw(self, surface, player):
        PW, PH = 560, 300
        px, py = (s.SCREEN_W - PW) // 2, (s.SCREEN_H - PH) // 2
        bg = gfx.Surface((PW, PH), pygame.SRCALPHA)
        bg.fill((14, 10, 20, 230))
        surface.blit(bg, (px, py))
        pygame.draw.rect(surface, (110, 80, 140), (px, py, PW, PH), 1, border_radius=4)

        title = self._font_title.render("MERCANTE OMBROSO", True, (200, 170, 235))
        surface.blit(title, title.get_rect(centerx=px + PW // 2, top=py + 12))
        sub = self._font_small.render("\"Psst... roba che l'Alchimista non ha.\"", True, (140, 125, 160))
        surface.blit(sub, sub.get_rect(centerx=px + PW // 2, top=py + 44))
        surface.blit(self._font.render(f"Oro: {player.gold}", True, s.C_COIN), (px + 16, py + 70))

        for i, kind in enumerate(self.merchant.offers):
            name, desc, price = self.merchant.offer(kind, player)
            sold = kind in self.merchant.sold
            uy   = py + 108 + i * 50
            if i == self._sel:
                pygame.draw.rect(surface, (58, 44, 76), (px + 8, uy - 6, PW - 16, 44), border_radius=4)
                pygame.draw.rect(surface, (160, 120, 210), (px + 8, uy - 6, PW - 16, 44), 1, border_radius=4)
            ok = not sold and player.gold >= price
            surface.blit(self._font.render(name, True, (225, 215, 240) if ok else (115, 108, 125)), (px + 20, uy - 2))
            surface.blit(self._font_small.render(desc, True, (140, 130, 158)), (px + 20, uy + 19))
            txt = "Venduto" if sold else f"{price} oro"
            col = (120, 110, 130) if sold else ((220, 175, 45) if player.gold >= price else (110, 87, 22))
            lbl = self._font.render(txt, True, col)
            surface.blit(lbl, (px + PW - lbl.get_width() - 20, uy + 6))

        if self._msg_timer > 0:
            m = self._font.render(self._msg, True, (230, 130, 120) if self._msg_err else (180, 230, 150))
            surface.blit(m, m.get_rect(centerx=px + PW // 2, top=py + PH - 50))
        hint = AssetManager.get().ui_font(15).render(InputManager.get().label(
            "[↑↓] Scegli  |  [INVIO] Compra  |  [ESC] Esci",
            "[↑↓] Scegli  |  [{A}] Compra  |  [{B}] Esci"), True, (110, 104, 122))
        surface.blit(hint, hint.get_rect(centerx=px + PW // 2, bottom=py + PH - 8))
