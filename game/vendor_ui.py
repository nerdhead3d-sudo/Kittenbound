import math
import pygame
from game import settings as s
from game.asset_manager import AssetManager
from game.sound import play
from game.input import InputManager
from game import gfx
from game import spells
from game import equipment

_STATS_UPGRADES = [
    ("HP Max",      f"+{s.UPGRADE_HP_MAX_AMOUNT} HP max",   s.UPGRADE_HP_MAX_COST,    "hp_max"),
    ("Energia",     f"+{s.UPGRADE_ENERGY_MAX_AMOUNT} EN max", s.UPGRADE_ENERGY_MAX_COST, "energy_max"),
    ("Rigenerazione", f"+{s.UPGRADE_HP_REGEN_AMOUNT} HP/s",   s.UPGRADE_HP_REGEN_COST,  "hp_regen"),
    ("Ricarica",    f"+{s.UPGRADE_ENERGY_REGEN_AMOUNT} EN/s", s.UPGRADE_ENERGY_REGEN_COST, "energy_regen"),
    ("Forza", f"+{s.UPGRADE_MELEE_DMG_AMOUNT} danno melee", s.UPGRADE_MELEE_DMG_COST, "melee_dmg"),
    ("Pozione",     f"+1 pozione ({s.POTION_HEAL} HP)", s.POTION_COST, "potion"),
]

# descrizione lunga, a sinistra quando la riga è scelta
_STATS_DESC = {
    "hp_max":       f"Un cuore più forte: +{s.UPGRADE_HP_MAX_AMOUNT} punti vita massimi.",
    "energy_max":   f"Più energia per le magie: +{s.UPGRADE_ENERGY_MAX_AMOUNT} energia massima.",
    "hp_regen":     f"Le ferite si chiudono da sole: +{s.UPGRADE_HP_REGEN_AMOUNT} HP al secondo.",
    "energy_regen": f"L'energia torna più in fretta: +{s.UPGRADE_ENERGY_REGEN_AMOUNT} al secondo.",
    "melee_dmg":    f"Artigli più duri: +{s.UPGRADE_MELEE_DMG_AMOUNT} danno a ogni graffio.",
    "potion":       f"Cura {s.POTION_HEAL} HP quando serve. Ne porti al massimo {s.POTION_MAX}.",
}
_LORE_CPS = 55          # lettere al secondo del testo dell'Anziano



def upgrade_cost(player, upgrade_type: str, base_cost: int) -> int:
    """Il prezzo cresce di UPGRADE_COST_GROWTH a ogni acquisto dello stesso potenziamento."""
    if upgrade_type == "potion":            # consumabile: prezzo fisso
        return base_cost
    return round(base_cost * s.UPGRADE_COST_GROWTH ** player.upgrades.get(upgrade_type, 0))


_LORE_TEXTS = [
    "Il regno dei Felini Arcani fu prospero per mille anni.",
    "I Topi della Congrega Oscura rubarono il Grimorio Perduto.",
    "Le ossa dei caduti vengono animate dalla magia oscura dei topi.",
    "Solo chi discende nelle profondità può sperare di recuperarlo.",
    "L'Oracolo predisse: 'Uno solo scenderà... e ritornerà.'",
]


class VendorUI:
    def __init__(self):
        assets = AssetManager.get()
        self._font_title = assets.font(24, bold=True)
        self._font       = assets.font(18)
        self._font_small = assets.font(15)
        self._msg        = ""
        self._msg_timer  = 0.0
        self._type       = 'stats'
        self._lore_idx   = 0
        self._sel        = 0      # riga selezionata (frecce / croce del controller)
        self._msg_err    = False
        self._lore_t     = 0.0    # da quanto è aperta la pagina dell'Anziano (testo che scorre)

    def open(self, vendor_type: str):
        self._type      = vendor_type
        self._msg       = ""
        self._msg_timer = 0.0
        self._lore_t    = 0.0
        self._sel       = 0

    def update(self, dt: float):
        if self._msg_timer > 0:
            self._msg_timer = max(0.0, self._msg_timer - dt)
        self._lore_t += dt

    def handle_key(self, key, player) -> bool:
        """Restituisce True se il vendor va chiuso."""
        if key in (pygame.K_e, pygame.K_ESCAPE):
            return True

        if self._type == 'stats':
            return self._handle_stats(key, player)
        if self._type == 'lore':
            return self._handle_lore(key)
        return self._handle_spell(key, player)

    def _handle_spell(self, key, player) -> bool:
        """Mago: compra una magia, oppure equipaggiala nello slot 1 (INVIO / A) o 2 (R / X)."""
        n = len(spells.ORDER)
        if key in (pygame.K_UP, pygame.K_w):
            self._sel = (self._sel - 1) % n
            play("ui_open", 0.3)
            return False
        if key in (pygame.K_DOWN, pygame.K_s):
            self._sel = (self._sel + 1) % n
            play("ui_open", 0.3)
            return False
        if key not in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_r):
            return False
        spell_id = spells.ORDER[self._sel % n]
        spell    = spells.SPELLS[spell_id]
        if spell_id not in player.spells_owned:
            if player.gold < spell.price:
                self._say("Oro insufficiente!", error=True)
                return False
            player.gold -= spell.price
            player.spells_owned.append(spell_id)
            play("buy", 0.8)
        slot  = 1 if key == pygame.K_r else 0
        other = 1 - slot
        if player.spell_slots[other] == spell_id:           # era nell'altro slot: scambio
            player.spell_slots[other] = player.spell_slots[slot]
        player.spell_slots[slot] = spell_id
        key_name = InputManager.get().label("F" if slot == 0 else "R", "{Y}" if slot == 0 else "{B}")
        self._say(f"{spell.name} su {key_name}")
        play("spell_mark", 0.6)
        return False

    def _say(self, text: str, error: bool = False):
        self._msg, self._msg_timer, self._msg_err = text, 1.5, error
        if error:
            play("error", 0.6)

    def _handle_stats(self, key, player) -> bool:
        idx_map = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2,
                   pygame.K_4: 3, pygame.K_5: 4, pygame.K_6: 5}
        n = len(_STATS_UPGRADES)
        if key in (pygame.K_UP, pygame.K_w):
            self._sel = (self._sel - 1) % n
            play("ui_open", 0.3)
            return False
        if key in (pygame.K_DOWN, pygame.K_s):
            self._sel = (self._sel + 1) % n
            play("ui_open", 0.3)
            return False
        if key in (pygame.K_RETURN, pygame.K_SPACE):
            idx = self._sel
        elif key in idx_map:
            idx = self._sel = idx_map[key]
        else:
            return False
        name, _, base_cost, upgrade_type = _STATS_UPGRADES[idx]
        cost = upgrade_cost(player, upgrade_type, base_cost)
        if upgrade_type == "potion" and player.potions >= s.POTION_MAX:
            self._say("Borsa piena!", error=True)
            return False
        if player.gold < cost:
            self._say("Oro insufficiente!", error=True)
            return False
        player.gold -= cost
        self._apply(player, upgrade_type)
        play("buy", 0.8)
        if upgrade_type == "potion":
            self._say(f"Pozione comprata ({player.potions}/{s.POTION_MAX})")
        else:
            player.upgrades[upgrade_type] = player.upgrades.get(upgrade_type, 0) + 1
            self._say(f"{name} migliorato")
        return False

    def _handle_lore(self, key) -> bool:
        if key in (pygame.K_SPACE, pygame.K_RETURN):
            if self._lore_t * _LORE_CPS < len(_LORE_TEXTS[self._lore_idx]):   # prima finisce la frase
                self._lore_t = 99.0
            else:
                self._lore_idx = (self._lore_idx + 1) % len(_LORE_TEXTS)
                self._lore_t   = 0.0
                play("page", 0.7)
        return False

    def _apply(self, player, upgrade_type: str):
        if upgrade_type == "hp_max":
            player.hp_max += s.UPGRADE_HP_MAX_AMOUNT
        elif upgrade_type == "energy_max":
            player.energy_max += s.UPGRADE_ENERGY_MAX_AMOUNT
        elif upgrade_type == "hp_regen":
            player.hp_regen_bonus += s.UPGRADE_HP_REGEN_AMOUNT
        elif upgrade_type == "energy_regen":
            player.energy_regen_bonus += s.UPGRADE_ENERGY_REGEN_AMOUNT
        elif upgrade_type == "melee_dmg":
            player.melee_damage_bonus += s.UPGRADE_MELEE_DMG_AMOUNT
        elif upgrade_type == "potion":
            player.potions += 1

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, player):
        if self._type == 'stats':
            self._draw_stats(surface, player)
        elif self._type == 'spell':
            self._draw_spell(surface, player)
        elif self._type == 'lore':
            self._draw_lore(surface)

    def _draw_panel(self, surface, pw, ph):
        px = (s.SCREEN_W - pw) // 2
        py = (s.SCREEN_H - ph) // 2
        bg = gfx.Surface((pw, ph), pygame.SRCALPHA)
        bg.fill((15, 13, 20, 220))
        surface.blit(bg, (px, py))
        pygame.draw.rect(surface, (80, 75, 100), (px, py, pw, ph), 1, border_radius=4)
        return px, py

    def _draw_stats(self, surface, player):
        """Alchimista, stile moderno come il Mago."""
        from game import shop_ui
        n    = len(_STATS_UPGRADES)
        sel  = self._sel % n
        rows = []
        for name, desc, base_cost, kind in _STATS_UPGRADES:
            cost = upgrade_cost(player, kind, base_cost)
            full = kind == "potion" and player.potions >= s.POTION_MAX
            if full:
                tag = ("Piena", shop_ui.BLUEISH, False)
            else:
                tag = (str(cost), shop_ui.GOLD_OK if player.gold >= cost else shop_ui.GOLD_NO, True)
            rows.append({"icon": shop_ui.icon(kind, 46), "name": name, "sub": desc, "tag": tag, "dim": full})
        name, desc, base_cost, kind = _STATS_UPGRADES[sel]
        cost   = upgrade_cost(player, kind, base_cost)
        level  = player.upgrades.get(kind, 0)
        status = (f"{cost} oro", shop_ui.GOLD_OK if player.gold >= cost else shop_ui.GOLD_NO)
        if kind == "potion":
            line = (f"Nella borsa: {player.potions}/{s.POTION_MAX}", shop_ui.BLUEISH)
            if player.potions >= s.POTION_MAX:
                status = ("Borsa piena", shop_ui.BLUEISH)
        else:
            line = (f"Livello {level}", shop_ui.GREEN) if level else ("Non ancora preso", (150, 146, 160))
        detail = {"icon": shop_ui.icon(kind, 180), "color": shop_ui.glow_color(kind), "name": name,
                  "desc": _STATS_DESC.get(kind, desc), "line": line, "status": status}
        msg = (self._msg, self._msg_timer / 0.4, self._msg_err) if self._msg_timer > 0 else None
        shop_ui.draw(surface, overline="ALCHIMISTA", title="Potenziamenti", gold=player.gold, rows=rows,
                     sel=sel, detail=detail, msg=msg, hints=[("confirm", "Compra"), ("back", "Esci")])

    def _draw_spell(self, surface, player):
        """Mago: a sinistra la magia scelta in grande, a destra la lista."""
        from game import shop_ui
        pad = InputManager.get()
        sel = self._sel % len(spells.ORDER)

        def key_of(spell_id):
            slot = player.spell_slots.index(spell_id)
            return pad.label("F" if slot == 0 else "R", "{Y}" if slot == 0 else "{B}")

        rows = []
        for spell_id in spells.ORDER:
            spi = spells.SPELLS[spell_id]
            if spell_id in player.spell_slots:
                tag = (key_of(spell_id), shop_ui.GREEN, False)
            elif spell_id in player.spells_owned:
                tag = ("Tua", shop_ui.BLUEISH, False)
            else:
                tag = (str(spi.price), shop_ui.GOLD_OK if player.gold >= spi.price else shop_ui.GOLD_NO, True)
            rows.append({"icon": shop_ui.icon(f"spell_{spell_id}", 46), "name": spi.name, "tag": tag})
        sid = spells.ORDER[sel]
        sp  = spells.SPELLS[sid]
        if sid in player.spell_slots:
            status = (f"Equipaggiata su {key_of(sid)}", shop_ui.GREEN)
        elif sid in player.spells_owned:
            status = ("Tua", shop_ui.BLUEISH)
        else:
            status = (f"{sp.price} oro", shop_ui.GOLD_OK if player.gold >= sp.price else shop_ui.GOLD_NO)
        detail = {"icon": shop_ui.icon(f"spell_{sid}", 190), "color": sp.color, "name": sp.name,
                  "desc": sp.desc, "line": (f"{sp.cost} energia", (246, 196, 72)), "status": status}
        buy = "Compra" if sid not in player.spells_owned else "Metti su " + pad.label("F", "{Y}")
        msg = (self._msg, self._msg_timer / 0.4, self._msg_err) if self._msg_timer > 0 else None
        shop_ui.draw(surface, overline="MAGO", title="Magie", gold=player.gold, rows=rows, sel=sel,
                     detail=detail, msg=msg,
                     hints=[("confirm", buy), ("second", "Metti su " + pad.label("R", "{B}")), ("back", "Esci")])

    def _draw_lore(self, surface):
        """Anziano: riquadro di dialogo in basso, il testo compare a poco a poco."""
        from game.menu import _font, _spaced, _panel, WHITE
        from game import controls_panel, shop_ui
        W, H = s.SCREEN_W, s.SCREEN_H
        shade = gfx.Surface((W, 280), pygame.SRCALPHA)
        for y in range(0, 280, 4):
            pygame.draw.rect(shade, (8, 6, 12, round(235 * (y / 280) ** 1.4)), (0, y, W, 4))
        surface.blit(shade, (0, H - 280))
        bw, bh = 820, 150
        box = pygame.Rect((W - bw) // 2, H - bh - 58, bw, bh)
        _panel(surface, box, fill=(16, 13, 22, 235), border=(255, 220, 160, 60), radius=16)
        gold = (226, 200, 140)
        surface.blit(_spaced("ANZIANO", _font(13, "bold"), gold, 5), (box.x + 28, box.y + 20))
        text  = _LORE_TEXTS[self._lore_idx]
        shown = text[:int(self._lore_t * _LORE_CPS)]
        font  = _font(22)
        line, y = "", box.y + 52
        for word in shown.split(" "):
            test = (line + " " + word).strip()
            if font.size(test)[0] > bw - 56 and line:
                surface.blit(font.render(line, True, WHITE), (box.x + 28, y))
                y += font.get_height() + 4
                line = word
            else:
                line = test
        if line:
            surface.blit(font.render(line, True, WHITE), (box.x + 28, y))
        n = len(_LORE_TEXTS)                                 # pallini delle pagine
        for k in range(n):
            cx = box.right - 28 - (n - 1 - k) * 16
            pygame.draw.circle(surface, gold if k == self._lore_idx else (80, 74, 90), (cx, box.y + 28), 4)
        x, y = box.x + 4, box.bottom + 18
        done = len(shown) >= len(text)
        for action, label in (("confirm", "Avanti" if done else "Salta"), ("back", "Esci")):
            w = controls_panel.draw_button(surface, action, x + 14, y + 10)
            x += max(w, 28) + 8
            f = shop_ui.txt_font(16)
            surface.blit(f.render(label, True, (170, 165, 180)), (x, y))
            x += f.size(label)[0] + 30
