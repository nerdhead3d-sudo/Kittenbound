import pygame
from game import settings as s
from game.asset_manager import AssetManager

_STATS_UPGRADES = [
    ("HP Max",      f"+{s.UPGRADE_HP_MAX_AMOUNT} HP max",   s.UPGRADE_HP_MAX_COST,    "hp_max"),
    ("Energia",     f"+{s.UPGRADE_ENERGY_MAX_AMOUNT} EN max", s.UPGRADE_ENERGY_MAX_COST, "energy_max"),
    ("Rig. HP",     f"+{s.UPGRADE_HP_REGEN_AMOUNT} HP/s",   s.UPGRADE_HP_REGEN_COST,  "hp_regen"),
    ("Rig. EN",     f"+{s.UPGRADE_ENERGY_REGEN_AMOUNT} EN/s", s.UPGRADE_ENERGY_REGEN_COST, "energy_regen"),
    ("Forza", f"+{s.UPGRADE_MELEE_DMG_AMOUNT} danno melee", s.UPGRADE_MELEE_DMG_COST, "melee_dmg"),
]

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
        return False   # spell: nessun tasto utile per ora

    def _handle_stats(self, key, player) -> bool:
        idx_map = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2,
                   pygame.K_4: 3, pygame.K_5: 4}
        if key not in idx_map:
            return False
        idx = idx_map[key]
        name, _, cost, upgrade_type = _STATS_UPGRADES[idx]
        if player.gold < cost:
            self._msg       = "Oro insufficiente!"
            self._msg_timer = 1.5
            return False
        player.gold -= cost
        self._apply(player, upgrade_type)
        self._msg       = f"{name} migliorato!"
        self._msg_timer = 1.5
        return False

    def _handle_lore(self, key) -> bool:
        if key in (pygame.K_SPACE, pygame.K_RETURN):
            self._lore_idx = (self._lore_idx + 1) % len(_LORE_TEXTS)
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

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, player):
        if self._type == 'stats':
            self._draw_stats(surface, player)
        elif self._type == 'spell':
            self._draw_spell(surface)
        elif self._type == 'lore':
            self._draw_lore(surface)

    def _draw_panel(self, surface, pw, ph):
        px = (s.SCREEN_W - pw) // 2
        py = (s.SCREEN_H - ph) // 2
        bg = pygame.Surface((pw, ph), pygame.SRCALPHA)
        bg.fill((15, 13, 20, 220))
        surface.blit(bg, (px, py))
        pygame.draw.rect(surface, (80, 75, 100), (px, py, pw, ph), 1, border_radius=4)
        return px, py

    def _draw_stats(self, surface, player):
        PW, PH = 420, 320
        px, py = self._draw_panel(surface, PW, PH)

        title = self._font_title.render("ALCHIMISTA", True, (210, 205, 228))
        surface.blit(title, title.get_rect(centerx=px + PW // 2, top=py + 12))

        gold_txt = self._font.render(f"Oro: {player.gold}", True, s.C_COIN)
        surface.blit(gold_txt, (px + 16, py + 46))

        for i, (name, desc, cost, _) in enumerate(_STATS_UPGRADES):
            uy = py + 82 + i * 38
            can_afford = player.gold >= cost
            key_col  = (200, 200, 80)  if can_afford else (100, 100, 80)
            name_col = (220, 215, 230) if can_afford else (110, 108, 115)
            cost_col = (220, 175, 45)  if can_afford else (110, 87, 22)
            surface.blit(self._font.render(f"[{i+1}]", True, key_col),        (px + 16, uy))
            surface.blit(self._font.render(name, True, name_col),              (px + 52, uy))
            surface.blit(self._font_small.render(desc, True, (130, 125, 145)), (px + 162, uy + 3))
            cost_s = self._font.render(f"{cost} oro", True, cost_col)
            surface.blit(cost_s, (px + PW - cost_s.get_width() - 16, uy))

        if self._msg_timer > 0:
            msg_s = self._font.render(self._msg, True, (180, 230, 150))
            surface.blit(msg_s, msg_s.get_rect(centerx=px + PW // 2, top=py + PH - 44))

        hint = self._font_small.render("[E] / [ESC] Chiudi", True, (80, 75, 90))
        surface.blit(hint, hint.get_rect(centerx=px + PW // 2, bottom=py + PH - 8))

    def _draw_spell(self, surface):
        PW, PH = 380, 200
        px, py = self._draw_panel(surface, PW, PH)

        title = self._font_title.render("MAGO", True, (210, 190, 240))
        surface.blit(title, title.get_rect(centerx=px + PW // 2, top=py + 14))

        msg = self._font.render("Nuove magie in arrivo...", True, (160, 145, 185))
        surface.blit(msg, msg.get_rect(centerx=px + PW // 2, centery=py + PH // 2 - 10))

        hint = self._font_small.render("[E] / [ESC] Chiudi", True, (80, 75, 90))
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

        hint = self._font_small.render(
            "[SPAZIO] Prossimo  |  [E] / [ESC] Chiudi", True, (80, 75, 90))
        surface.blit(hint, hint.get_rect(centerx=px + PW // 2, bottom=py + PH - 8))
