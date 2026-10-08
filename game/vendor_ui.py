import pygame
from game import settings as s
from game.asset_manager import AssetManager
from game.sound import play
from game.input import InputManager
from game import gfx
from game import spells

_STATS_UPGRADES = [
    ("HP Max",      f"+{s.UPGRADE_HP_MAX_AMOUNT} HP max",   s.UPGRADE_HP_MAX_COST,    "hp_max"),
    ("Energia",     f"+{s.UPGRADE_ENERGY_MAX_AMOUNT} EN max", s.UPGRADE_ENERGY_MAX_COST, "energy_max"),
    ("Rig. HP",     f"+{s.UPGRADE_HP_REGEN_AMOUNT} HP/s",   s.UPGRADE_HP_REGEN_COST,  "hp_regen"),
    ("Rig. EN",     f"+{s.UPGRADE_ENERGY_REGEN_AMOUNT} EN/s", s.UPGRADE_ENERGY_REGEN_COST, "energy_regen"),
    ("Forza", f"+{s.UPGRADE_MELEE_DMG_AMOUNT} danno melee", s.UPGRADE_MELEE_DMG_COST, "melee_dmg"),
    ("Pozione",     f"+1 pozione ({s.POTION_HEAL} HP, Q)", s.POTION_COST, "potion"),
]



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

    def open(self, vendor_type: str):
        self._type      = vendor_type
        self._msg       = ""
        self._msg_timer = 0.0

    def update(self, dt: float):
        if self._msg_timer > 0:
            self._msg_timer = max(0.0, self._msg_timer - dt)

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
        self._msg, self._msg_timer = text, 1.5
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
            self._msg       = "Borsa piena!"
            play("error", 0.6)
            self._msg_timer = 1.5
            return False
        if player.gold < cost:
            self._msg       = "Oro insufficiente!"
            play("error", 0.6)
            self._msg_timer = 1.5
            return False
        player.gold -= cost
        self._apply(player, upgrade_type)
        play("buy", 0.8)
        if upgrade_type == "potion":
            self._msg = f"Pozione acquistata! ({player.potions}/{s.POTION_MAX})"
        else:
            player.upgrades[upgrade_type] = player.upgrades.get(upgrade_type, 0) + 1
            self._msg = f"{name} migliorato!"
        self._msg_timer = 1.5
        return False

    def _handle_lore(self, key) -> bool:
        if key in (pygame.K_SPACE, pygame.K_RETURN):
            self._lore_idx = (self._lore_idx + 1) % len(_LORE_TEXTS)
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
        PW, PH = 480, 360
        px, py = self._draw_panel(surface, PW, PH)

        title = self._font_title.render("ALCHIMISTA", True, (210, 205, 228))
        surface.blit(title, title.get_rect(centerx=px + PW // 2, top=py + 12))

        gold_txt = self._font.render(f"Oro: {player.gold}", True, s.C_COIN)
        surface.blit(gold_txt, (px + 16, py + 46))

        for i, (name, desc, base_cost, upgrade_type) in enumerate(_STATS_UPGRADES):
            cost = upgrade_cost(player, upgrade_type, base_cost)
            level = player.upgrades.get(upgrade_type, 0)
            uy = py + 82 + i * 38
            if i == self._sel:
                pygame.draw.rect(surface, (60, 54, 80), (px + 8, uy - 6, PW - 16, 32), border_radius=4)
                pygame.draw.rect(surface, (150, 130, 200), (px + 8, uy - 6, PW - 16, 32), 1, border_radius=4)
            can_afford = player.gold >= cost
            key_col  = (200, 200, 80)  if can_afford else (100, 100, 80)
            name_col = (220, 215, 230) if can_afford else (110, 108, 115)
            cost_col = (220, 175, 45)  if can_afford else (110, 87, 22)
            surface.blit(self._font.render(f"[{i+1}]", True, key_col),        (px + 16, uy))
            surface.blit(self._font.render(name, True, name_col),              (px + 52, uy))
            surface.blit(self._font_small.render(desc, True, (130, 125, 145)), (px + 162, uy + 3))
            if upgrade_type == "potion":
                full = player.potions >= s.POTION_MAX
                lv_s = self._font_small.render(f"{player.potions}/{s.POTION_MAX}", True,
                                               (220, 120, 110) if full else (150, 200, 150))
                surface.blit(lv_s, (px + PW - 140, uy + 3))
            elif level:
                lv_s = self._font_small.render(f"Lv{level}", True, (150, 200, 150))
                surface.blit(lv_s, (px + PW - 140, uy + 3))
            cost_s = self._font.render(f"{cost} oro", True, cost_col)
            surface.blit(cost_s, (px + PW - cost_s.get_width() - 16, uy))

        if self._msg_timer > 0:
            msg_s = self._font.render(self._msg, True, (180, 230, 150))
            surface.blit(msg_s, msg_s.get_rect(centerx=px + PW // 2, top=py + PH - 44))

        hint = AssetManager.get().ui_font(15).render(InputManager.get().label(
            "[1-6] / [\u2191\u2193 + INVIO] Compra  |  [E] / [ESC] Chiudi",
            "[\u2191\u2193] Scegli  |  [{A}] Compra  |  [{B}] Chiudi"), True, (110, 104, 122))
        surface.blit(hint, hint.get_rect(centerx=px + PW // 2, bottom=py + PH - 8))

    def _draw_spell(self, surface, player):
        PW, PH = 700, 420
        px, py = self._draw_panel(surface, PW, PH)
        pad = InputManager.get()

        title = self._font_title.render("MAGO", True, (210, 190, 240))
        surface.blit(title, title.get_rect(centerx=px + PW // 2, top=py + 12))
        surface.blit(self._font.render(f"Oro: {player.gold}", True, s.C_COIN), (px + 16, py + 46))
        sub = self._font_small.render("Puoi portare 2 magie alla volta", True, (150, 140, 175))
        surface.blit(sub, sub.get_rect(right=px + PW - 16, top=py + 49))

        for i, spell_id in enumerate(spells.ORDER):
            sp    = spells.SPELLS[spell_id]
            owned = spell_id in player.spells_owned
            uy    = py + 84 + i * 46
            if i == self._sel % len(spells.ORDER):
                pygame.draw.rect(surface, (60, 54, 80), (px + 8, uy - 6, PW - 16, 42), border_radius=4)
                pygame.draw.rect(surface, (150, 130, 200), (px + 8, uy - 6, PW - 16, 42), 1, border_radius=4)
            pygame.draw.circle(surface, sp.color, (px + 26, uy + 14), 7)
            name_col = (225, 220, 235) if owned or player.gold >= sp.price else (120, 116, 128)
            surface.blit(self._font.render(sp.name, True, name_col), (px + 42, uy - 2))
            surface.blit(self._font_small.render(f"{sp.desc}  ·  {sp.cost} EN", True, (135, 128, 150)),
                         (px + 42, uy + 18))
            if spell_id in player.spell_slots:                   # equipaggiata: su quale tasto
                slot = player.spell_slots.index(spell_id)
                tag  = pad.label("F" if slot == 0 else "R", "{Y}" if slot == 0 else "{B}")
                txt, col = f"[{tag}]", (150, 230, 150)
            elif owned:
                txt, col = "Tua", (150, 170, 200)
            else:
                txt = f"{sp.price} oro"
                col = (220, 175, 45) if player.gold >= sp.price else (110, 87, 22)
            lbl = AssetManager.get().ui_font(18).render(txt, True, col)
            surface.blit(lbl, (px + PW - lbl.get_width() - 18, uy + 4))

        if self._msg_timer > 0:
            msg_s = self._font.render(self._msg, True, (180, 230, 150))
            surface.blit(msg_s, msg_s.get_rect(centerx=px + PW // 2, top=py + PH - 50))

        hint = AssetManager.get().ui_font(15).render(pad.label(
            "[\u2191\u2193] Scegli  |  [INVIO] Compra, metti su F  |  [R] Metti su R  |  [ESC] Esci",
            "[\u2191\u2193] Scegli  |  [{A}/{Y}] Compra, metti su {Y}  |  [{X}] Metti su {B}  |  [{B}] Esci"),
            True, (110, 104, 122))
        surface.blit(hint, hint.get_rect(centerx=px + PW // 2, bottom=py + PH - 8))

    def _draw_lore(self, surface):
        PW, PH = 520, 240
        px, py = self._draw_panel(surface, PW, PH)

        title = self._font_title.render("ANZIANO", True, (210, 195, 150))
        surface.blit(title, title.get_rect(centerx=px + PW // 2, top=py + 14))

        idx_txt = self._font_small.render(
            f"{self._lore_idx + 1}/{len(_LORE_TEXTS)}", True, (100, 95, 80))
        surface.blit(idx_txt, idx_txt.get_rect(right=px + PW - 12, top=py + 18))

        text  = _LORE_TEXTS[self._lore_idx]
        words = text.split()
        lines, line = [], ""
        for w in words:
            test = (line + " " + w).strip()
            if self._font.size(test)[0] < PW - 48:
                line = test
            else:
                lines.append(line)
                line = w
        if line:
            lines.append(line)

        for i, ln in enumerate(lines):
            surf = self._font.render(ln, True, (200, 190, 160))
            surface.blit(surf, surf.get_rect(centerx=px + PW // 2, top=py + 70 + i * 30))

        hint = AssetManager.get().ui_font(15).render(
            InputManager.get().label("[SPAZIO] Prossimo  |  [E] / [ESC] Chiudi",
                                     "[{A}] Prossimo  |  [{B}] Chiudi"), True, (110, 104, 122))
        surface.blit(hint, hint.get_rect(centerx=px + PW // 2, bottom=py + PH - 8))
