import math
import pygame
from game import settings as s
from game.asset_manager import AssetManager

ENTRANCE_POS     = (640,  90)    # top center — entrata dungeon in pietra
GATE_POS         = (1080, 230)   # top right — gate recall (appare dopo G)
VENDOR_SPELL_POS = (190,  390)
VENDOR_STATS_POS = (480,  470)
VENDOR_LORE_POS  = (870,  390)
SPAWN_POS        = (640,  560)   # inizio percorso (player spawna qui)
RETURN_POS       = (1080, 320)   # sotto il gate

_C_GRASS      = (52,  92,  42)
_C_GRASS_ALT  = (46,  84,  36)
_C_PATH       = (118, 90,  60)
_C_PATH_ALT   = (106, 82,  54)
_C_TRUNK      = (72,  52,  32)
_C_LEAF       = (35,  68,  25)
_C_LEAF_LT    = (52,  95,  38)
_C_STONE      = (88,  82,  75)
_C_STONE_DK   = (68,  62,  55)
_C_CAVE       = (18,  15,  22)

_PATH_X1 = 608
_PATH_X2 = 672
_PATH_Y1 = 116      # parte dall'entrata...
_PATH_Y2 = 635      # ...fino quasi in fondo allo schermo

# (cx, cy, raggio_foglie) — posizioni fisse degli alberi
_TREES = [
    ( 95, 140, 38), (330, 115, 30), (900, 125, 32), (1155, 145, 36),
    ( 55, 290, 34), (1195, 280, 30),
    ( 70, 470, 38), (295, 570, 28), (960, 565, 30), (1185, 460, 34),
    (365, 195, 26), (855, 180, 28), (1040, 360, 22),
    (135, 635, 30), (425, 635, 24), (815, 625, 26), (1120, 620, 32),
    (215, 335, 24),
    # alberi vicino all'entrata per incorniciare il dungeon
    (530, 100, 26), (750, 100, 24),
]


class Hub:
    def __init__(self):
        self._font = AssetManager.get().font(16)
        self.gate_active = False

    def activate_gate(self):
        self.gate_active = True

    def enter(self, player):
        player.pos.x = float(SPAWN_POS[0])
        player.pos.y = float(SPAWN_POS[1])
        player.rect.center = SPAWN_POS

    def enter_from_dungeon(self, player):
        player.pos.x = float(RETURN_POS[0])
        player.pos.y = float(RETURN_POS[1])
        player.rect.center = (round(RETURN_POS[0]), round(RETURN_POS[1]))

    def get_interaction(self, player_pos) -> str | None:
        px, py = float(player_pos[0]), float(player_pos[1])

        for (vx, vy), tag in [
            (VENDOR_SPELL_POS, 'vendor_spell'),
            (VENDOR_STATS_POS, 'vendor_stats'),
            (VENDOR_LORE_POS,  'vendor_lore'),
            (ENTRANCE_POS,     'entrance'),
        ]:
            if (px - vx) ** 2 + (py - vy) ** 2 <= s.VENDOR_INTERACT_RADIUS ** 2:
                return tag

        if self.gate_active:
            gx, gy = GATE_POS
            if (px - gx) ** 2 + (py - gy) ** 2 <= s.ENTRANCE_INTERACT_RADIUS ** 2:
                return 'gate'

        return None

    def draw(self, surface: pygame.Surface, player_pos):
        # Erba
        surface.fill(_C_GRASS)
        ts = 64
        for row in range(0, s.SCREEN_H, ts):
            for col in range(0, s.SCREEN_W, ts):
                if ((row // ts) + (col // ts)) % 2 == 0:
                    pygame.draw.rect(surface, _C_GRASS_ALT, (col, row, ts, ts))

        self._draw_path(surface)
        self._draw_trees(surface)
        self._draw_vendor_spell(surface, player_pos)
        self._draw_vendor_stats(surface, player_pos)
        self._draw_vendor_lore(surface, player_pos)
        self._draw_entrance(surface, player_pos)
        if self.gate_active:
            self._draw_gate(surface, player_pos)

    # ── Sentiero ──────────────────────────────────────────────────────────────

    def _draw_path(self, surface):
        w = _PATH_X2 - _PATH_X1
        h = _PATH_Y2 - _PATH_Y1
        pygame.draw.rect(surface, _C_PATH, (_PATH_X1, _PATH_Y1, w, h))
        ts = 32
        for ty in range(_PATH_Y1, _PATH_Y2, ts):
            for tx in range(_PATH_X1, _PATH_X2, ts):
                if ((ty // ts) + (tx // ts)) % 2 == 0:
                    pygame.draw.rect(surface, _C_PATH_ALT, (tx, ty, ts, ts))

    # ── Alberi ────────────────────────────────────────────────────────────────

    def _draw_trees(self, surface):
        assets = AssetManager.get()
        for cx, cy, r in _TREES:          # ombre prima, così nessuna copre un tronco
            sh = assets.shadow(r * 2 + 16, r)
            surface.blit(sh, sh.get_rect(center=(cx + 10, cy + r + 4)))
        for cx, cy, r in _TREES:
            tw = max(8, r // 3)
            th = r // 2 + 4
            pygame.draw.rect(surface, _C_TRUNK, (cx - tw // 2, cy + r - 6, tw, th))
            pygame.draw.circle(surface, _C_LEAF, (cx, cy), r)
            pygame.draw.circle(surface, _C_LEAF_LT, (cx - r // 4, cy - r // 4), r // 3)

    # ── NPC helper ────────────────────────────────────────────────────────────

    def _draw_npc(self, surface, pos, body_col, head_col, label, hint_text, player_pos):
        vx, vy = pos
        sh = AssetManager.get().shadow(48, 16)
        surface.blit(sh, sh.get_rect(center=(vx + 3, vy + 20)))
        pygame.draw.circle(surface, body_col, (vx, vy), 22)
        pygame.draw.circle(surface, head_col, (vx, vy - 8), 14)
        pygame.draw.circle(surface, (20, 20, 25), (vx, vy - 8), 14, 2)
        lbl = self._font.render(label, True, (230, 220, 195))
        surface.blit(lbl, lbl.get_rect(centerx=vx, bottom=vy - 30))
        px, py = float(player_pos[0]), float(player_pos[1])
        if (px - vx) ** 2 + (py - vy) ** 2 <= s.VENDOR_INTERACT_RADIUS ** 2:
            hint = self._font.render(hint_text, True, (245, 235, 120))
            surface.blit(hint, hint.get_rect(centerx=vx, top=vy + 28))

    # ── Singoli NPC ───────────────────────────────────────────────────────────

    def _draw_vendor_spell(self, surface, player_pos):
        self._draw_npc(surface, VENDOR_SPELL_POS,
                       (140, 100, 180), (170, 130, 210),
                       "Mago", "[E] Magie", player_pos)

    def _draw_vendor_stats(self, surface, player_pos):
        self._draw_npc(surface, VENDOR_STATS_POS,
                       (100, 140, 180), (130, 170, 210),
                       "Alchimista", "[E] Potenziamenti", player_pos)

    def _draw_vendor_lore(self, surface, player_pos):
        self._draw_npc(surface, VENDOR_LORE_POS,
                       (160, 130, 80), (190, 160, 100),
                       "Anziano", "[E] Storia", player_pos)

    # ── Entrata dungeon (arco in pietra) ──────────────────────────────────────

    def _draw_entrance(self, surface, player_pos):
        ex, ey = ENTRANCE_POS
        aw, ah = 72, 52
        # interno buio
        pygame.draw.rect(surface, _C_CAVE,
                         (ex - aw // 2, ey - ah // 2, aw, ah))
        # pilastri laterali
        pygame.draw.rect(surface, _C_STONE,
                         (ex - aw // 2 - 10, ey - ah // 2 - 4, 13, ah + 4))
        pygame.draw.rect(surface, _C_STONE,
                         (ex + aw // 2 - 3,  ey - ah // 2 - 4, 13, ah + 4))
        # architrave
        pygame.draw.rect(surface, _C_STONE_DK,
                         (ex - aw // 2 - 10, ey - ah // 2 - 14, aw + 23, 13))
        # muschio sugli angoli
        pygame.draw.circle(surface, _C_LEAF, (ex - aw // 2 - 4, ey - ah // 2 + 2), 6)
        pygame.draw.circle(surface, _C_LEAF, (ex + aw // 2 + 4, ey - ah // 2 + 6), 5)

        lbl = self._font.render("Dungeon", True, (155, 150, 140))
        surface.blit(lbl, lbl.get_rect(centerx=ex, bottom=ey - ah // 2 - 16))

        px, py = float(player_pos[0]), float(player_pos[1])
        if (px - ex) ** 2 + (py - ey) ** 2 <= s.ENTRANCE_INTERACT_RADIUS ** 2:
            hint = self._font.render("[E] Entra nel dungeon", True, (245, 235, 120))
            surface.blit(hint, hint.get_rect(centerx=ex, top=ey + ah // 2 + 12))

    # ── Gate Recall ───────────────────────────────────────────────────────────

    def _draw_gate(self, surface, player_pos):
        gx, gy = GATE_POS
        t = pygame.time.get_ticks() / 1000.0
        r = int(22 + 4 * math.sin(t * 3.0))
        pygame.draw.circle(surface, (25, 12, 48),    (gx, gy), r + 14)
        pygame.draw.circle(surface, (120, 55, 190),  (gx, gy), r, 3)
        pygame.draw.circle(surface, (185, 130, 245), (gx, gy), r // 2)
        pygame.draw.circle(surface, (220, 200, 255), (gx, gy), 4)
        lbl = self._font.render("Gate Recall", True, (170, 130, 220))
        surface.blit(lbl, lbl.get_rect(centerx=gx, bottom=gy - 28))
        px, py = float(player_pos[0]), float(player_pos[1])
        if (px - gx) ** 2 + (py - gy) ** 2 <= s.ENTRANCE_INTERACT_RADIUS ** 2:
            hint = self._font.render("[E] Torna dove eri", True, (245, 235, 120))
            surface.blit(hint, hint.get_rect(centerx=gx, top=gy + 28))
