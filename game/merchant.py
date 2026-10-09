"""Mercante nascosto: in alcuni piani si nasconde in una stanza (di solito un vicolo cieco) e
esce dall'ombra solo quando la stanza è liberata. Vende 3 cose scelte a caso, ognuna una volta.

Non compare sulla mappa finché non lo trovi. Il modello è provvisorio: l'Alchimista dell'hub
scurito, con una luce sua, finché non c'è un modello suo.
"""
import math
import random

import pygame

from game import settings as s, gfx
from game.asset_manager import AssetManager
from game.input import InputManager
from game.sound import play
from game.vendor_ui import upgrade_cost
from game import equipment

# Potenziamento raro: il doppio del normale, a poco più del prezzo dell'Alchimista
_RARE = {
    "hp_max":     ("Cuore di Topo",   f"+{2 * s.UPGRADE_HP_MAX_AMOUNT} HP max",     s.UPGRADE_HP_MAX_COST),
    "energy_max": ("Coda Elettrica",  f"+{2 * s.UPGRADE_ENERGY_MAX_AMOUNT} EN max", s.UPGRADE_ENERGY_MAX_COST),
    "melee_dmg":  ("Artigli Affilati", f"+{2 * s.UPGRADE_MELEE_DMG_AMOUNT} danno melee", s.UPGRADE_MELEE_DMG_COST),
    "hp_regen":   ("Erba Gattaia",    f"+{2 * s.UPGRADE_HP_REGEN_AMOUNT:g} HP/s",   s.UPGRADE_HP_REGEN_COST),
}
OFFERS = ("potion", "elixir", "rare", "map", "audacia", "gear")


class Merchant:
    def __init__(self, x: float, y: float, rng: random.Random):
        self.pos      = pygame.math.Vector2(x, y)
        self.offers   = rng.sample(OFFERS, s.MERCHANT_OFFERS)
        self.rare     = rng.choice(list(_RARE))
        ids           = list(equipment.ITEMS)              # equipaggiamento in vendita (caro)
        self.gear     = rng.choices(ids, [{1: 50, 2: 35, 3: 15}[equipment.ITEMS[i].rarity] for i in ids])[0]
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
        if kind == "gear":
            it = equipment.ITEMS[self.gear]
            return (it.name, f"{equipment.RARITY_NAMES[it.rarity]} · {equipment.SLOT_NAMES[it.slot]}: {it.desc}",
                    s.EQUIP_PRICES[it.rarity])
        name, desc, base = _RARE[self.rare]
        return name, f"{desc} (raro)", round(upgrade_cost(player, self.rare, base) * s.MERCHANT_RARE_MULT)

    def buy(self, kind: str, player, dungeon) -> str | None:
        """Compra; restituisce il messaggio d'errore o None se è andata."""
        if kind in self.sold:
            return "Già venduto"
        _, _, price = self.offer(kind, player)
        if kind == "gear" and equipment.owns(player, self.gear):
            return "Ce l'hai già"
        if kind == "gear" and len(player.backpack) >= equipment.BACKPACK_SIZE and \
                player.equipment.get(equipment.ITEMS[self.gear].slot):
            return "Zaino pieno"
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
        elif kind == "gear":
            equipment.give(player, self.gear)
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

        shadow = gfx.Surface((60, 16), pygame.SRCALPHA)        # solo l'ombra: niente oggetti finti a terra
        pygame.draw.ellipse(shadow, (0, 0, 0, 90), shadow.get_rect())
        surface.blit(shadow, (cx - 30, cy - 8))

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
        return round(self.pos.x), round(self.pos.y) - 30, s.MERCHANT_LIGHT_RADIUS


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
            self._say(err or "Affare fatto", err is not None)
        return False

    def _icon_kind(self, kind):
        if kind == "gear":
            return self.merchant.gear
        if kind == "rare":
            return self.merchant.rare
        return kind

    def draw(self, surface, player):
        from game import shop_ui
        m   = self.merchant
        sel = self._sel % len(m.offers)
        rows = []
        for kind in m.offers:
            name, desc, price = m.offer(kind, player)
            sold = kind in m.sold
            if sold:
                tag = ("Venduto", (130, 122, 140), False)
            else:
                tag = (str(price), shop_ui.GOLD_OK if player.gold >= price else shop_ui.GOLD_NO, True)
            rows.append({"icon": shop_ui.icon(self._icon_kind(kind), 46), "name": name, "tag": tag, "dim": sold})
        kind = m.offers[sel]
        name, desc, price = m.offer(kind, player)
        if kind in m.sold:
            status = ("Venduto", (150, 140, 160))
        else:
            status = (f"{price} oro", shop_ui.GOLD_OK if player.gold >= price else shop_ui.GOLD_NO)
        line = None
        if kind == "gear":
            it   = equipment.ITEMS[m.gear]
            line = (f"{equipment.RARITY_NAMES[it.rarity]} · {equipment.SLOT_NAMES[it.slot]}",
                    equipment.RARITY_COLORS[it.rarity])
            desc = it.desc
        elif kind == "rare":
            line = ("Raro: il doppio dell'Alchimista", (200, 160, 255))
            desc = desc.replace(" (raro)", "")
        ik = self._icon_kind(kind)
        detail = {"icon": shop_ui.icon(ik, 180), "color": shop_ui.glow_color(ik),
                  "name": name, "desc": desc, "line": line, "status": status}
        msg = (self._msg, self._msg_timer / 0.4, self._msg_err) if self._msg_timer > 0 else None
        shop_ui.draw(surface, overline="MERCANTE OMBROSO", title="Merce rara", gold=player.gold, rows=rows,
                     sel=sel, detail=detail, msg=msg, accent=(200, 160, 255),
                     hints=[("confirm", "Compra"), ("back", "Esci")])
