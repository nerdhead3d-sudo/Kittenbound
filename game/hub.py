import math
import random
import pygame
from game import settings as s
from game.asset_manager import AssetManager
from game.input import InputManager
from game import gfx

# Posizioni allineate allo sfondo dipinto (assets/sprites/bg_hub.png, 1280x720)
ENTRANCE_POS     = (655,  100)   # top center — entrata dungeon in pietra
GATE_POS         = (1110, 220)   # top right — gate recall sul cerchio di pietra (appare dopo G)
VENDOR_SPELL_POS = (182,  396)   # fine del ramo sinistro del sentiero
VENDOR_STATS_POS = (445,  494)   # fine del ramo in basso a sinistra
VENDOR_LORE_POS  = (912,  382)   # fine del ramo destro
SPAWN_POS        = (655,  640)   # inizio percorso (player spawna qui)
RETURN_POS       = (1110, 300)   # sotto il gate

# Sfondo dipinto: alberi (x, y della base del tronco, raggio della chioma) e sassi (x, y, raggio)
_BG_TREES = [
    (140,  45, 50), ( 52, 180, 58), (305, 132, 45), (370, 230, 40), (520, 122, 42),
    (795, 122, 40), (962, 155, 55), (885, 215, 42), (1155, 60, 50), (1210, 220, 60),
    (1235, 345, 50), ( 60, 345, 50), (250, 368, 40), (1050, 362, 37), ( 55, 550, 62),
    (1225, 552, 58), (968, 598, 55), (300, 620, 50), (130, 705, 52), (430, 688, 45),
    (840, 668, 45), (1150, 705, 60),
]
_BG_ROCKS = [(315, 18, 14), (740, 155, 14), (308, 365, 14), (1100, 45, 12), (1220, 78, 12),
             (1190, 383, 13), (12, 605, 16), (1012, 632, 13), (282, 685, 13)]
_BG_TORCHES = [(604, 50), (703, 50)]

_C_GRASS      = (58,  98,  44)
_C_GRASS_DK   = (44,  80,  34)
_C_GRASS_LT   = (78, 122,  56)
_C_PATH       = (124,  96,  64)
_C_PATH_DK    = (92,  70,  46)
_C_TRUNK      = (84,  60,  38)
_C_TRUNK_DK   = (56,  40,  26)
_C_LEAF_DK    = (30,  58,  24)
_C_LEAF       = (44,  82,  32)
_C_LEAF_LT    = (70, 112,  46)
_C_STONE      = (112, 106,  98)
_C_STONE_DK   = (74,  69,  64)
_C_STONE_LT   = (146, 140, 130)
_C_CAVE       = (14,  11,  18)

# (cx, cy, raggio_chioma) — posizioni fisse degli alberi (cy = centro della chioma)
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

# NPC: posizione, colori, accessorio
_NPCS = [
    dict(pos=VENDOR_SPELL_POS, tag="spell", name="Mago",       hint="[E] Magie", model="npc_mage",
         fur=(70, 66, 78),   robe=(112, 74, 164), eyes=(250, 210, 80)),
    dict(pos=VENDOR_STATS_POS, tag="stats", name="Alchimista", hint="[E] Potenziamenti", model="npc_alchemist",
         fur=(206, 134, 62), robe=(52, 116, 136), eyes=(120, 220, 120)),
    dict(pos=VENDOR_LORE_POS,  tag="lore",  name="Anziano",    hint="[E] Storia",
         fur=(212, 206, 196), robe=(128, 92, 58), eyes=(120, 170, 230)),
]
_NPC_FEET = 24          # i piedi stanno 24 px sotto la posizione (centro) dell'NPC


def _shade(c, d):
    return tuple(max(0, min(255, v + d)) for v in c)


def _glow(radius: int, color: tuple) -> pygame.Surface:
    """Alone radiale da sommare (BLEND_RGB_ADD): luce di torce, lucciole, magia."""
    surf = gfx.Surface((radius * 2, radius * 2))
    for r in range(radius, 0, -2):
        f = (1 - r / radius) ** 2
        pygame.draw.circle(surf, tuple(int(v * f) for v in color), (radius, radius), r)
    return surf


class Hub:
    """Radura iniziale in finto 3D: prato pre-renderizzato, alberi, NPC e ingresso
    del dungeon con altezza, ordinati per Y insieme al gatto (che può passare dietro)."""

    def __init__(self):
        self._font = AssetManager.get().font(16)
        self.gate_active = False

        bg_path = AssetManager.image_path("bg_hub")
        self._painted = bg_path.exists()                 # sfondo dipinto: alberi e grotta già disegnati
        if self._painted:                                # ricampionato una volta alla risoluzione reale
            self._ground = gfx.fit(pygame.image.load(str(bg_path)).convert(), (s.SCREEN_W, s.SCREEN_H))
            self._trees  = [self._cut_crown(self._ground, x, y, r) for x, y, r in _BG_TREES]
        else:
            self._ground = self._render_ground()
            self._trees  = [self._make_tree(cx, cy, r) for cx, cy, r in _TREES]
        self._vignette = self._render_vignette()
        self._npcs     = [dict(n, sprite=self._make_npc(n), anims=self._npc_anims(n)) for n in _NPCS]
        self._entrance = self._make_entrance()
        self._torch_glow = _glow(70, (255, 150, 60))
        self._torch_glow_soft = _glow(48, (120, 64, 22))   # sfondo dipinto: torce già accese
        self._firefly    = _glow(9, (190, 255, 120))
        self._orb_glow   = _glow(22, (170, 110, 255))
        rng = random.Random(4)
        self._fireflies = [(rng.uniform(0, s.SCREEN_W), rng.uniform(140, s.SCREEN_H),
                            rng.uniform(0, math.tau), rng.uniform(0.3, 0.8)) for _ in range(16)]

        # Ostacoli: tronchi, NPC, collina dell'ingresso (il gatto non ci passa attraverso)
        self.obstacles = [pygame.Rect(t["base"][0] - t["trunk_w"] // 2 - 2, t["base"][1] - 12,
                                      t["trunk_w"] + 4, 12) for t in self._trees]
        self.obstacles += [pygame.Rect(n["pos"][0] - 14, n["pos"][1] + _NPC_FEET - 12, 28, 12)
                           for n in self._npcs]
        if self._painted:
            self.obstacles.append(pygame.Rect(548, 0, 214, 92))                # roccia della grotta
            self.obstacles += [pygame.Rect(x - r, y - r // 2, r * 2, r) for x, y, r in _BG_ROCKS]
        else:
            self.obstacles.append(pygame.Rect(ENTRANCE_POS[0] - 96, ENTRANCE_POS[1] - 70, 192, 98))

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

    # ── Pre-render (una volta sola) ───────────────────────────────────────────

    def _render_ground(self) -> pygame.Surface:
        W, H = s.SCREEN_W, s.SCREEN_H
        rng  = random.Random(11)
        surf = gfx.Surface((W, H))
        surf.fill(_C_GRASS)

        patches = gfx.Surface((W, H), pygame.SRCALPHA)       # macchie più chiare/scure
        for _ in range(70):
            c = _C_GRASS_LT if rng.random() < 0.5 else _C_GRASS_DK
            pygame.draw.circle(patches, (*c, 40), (rng.randrange(W), rng.randrange(H)), rng.randint(30, 110))
        surf.blit(patches, (0, 0))

        for _ in range(3200):                                   # fili d'erba
            x, y = rng.randrange(W), rng.randrange(H)
            c = _shade(_C_GRASS, rng.randint(-22, 26))
            pygame.draw.line(surf, c, (x, y), (x + rng.randint(-2, 2), y - rng.randint(3, 7)))
        for _ in range(110):                                    # fiorellini
            x, y = rng.randrange(W), rng.randrange(H)
            c = rng.choice([(236, 232, 220), (244, 214, 92), (226, 150, 190), (176, 160, 236)])
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                pygame.draw.circle(surf, c, (x + dx, y + dy), 1)
            pygame.draw.circle(surf, (250, 230, 120), (x, y), 1)

        # Sentiero: bordo scuro sotto, terra sopra, così i margini restano irregolari
        path_pts = []
        for y in range(100, H + 30, 7):                         # tratto principale
            path_pts.append((640 + 7 * math.sin(y / 47), y, 33 + rng.randint(-3, 3)))
        for n in _NPCS:                                         # diramazioni verso i venditori
            vx, vy = n["pos"]
            fy = vy + _NPC_FEET + 6
            sx, sy = 640, fy + 50
            for i in range(26):
                t = i / 25
                cx = (1 - t) ** 2 * sx + 2 * (1 - t) * t * ((sx + vx) / 2) + t * t * vx
                cy = (1 - t) ** 2 * sy + 2 * (1 - t) * t * (fy + 30) + t * t * fy
                path_pts.append((cx, cy, 17 + rng.randint(-2, 2)))
        for x, y, r in path_pts:
            pygame.draw.circle(surf, _C_PATH_DK, (round(x), round(y)), r + 3)
        for x, y, r in path_pts:
            pygame.draw.circle(surf, _C_PATH, (round(x), round(y)), r)
        for x, y, r in path_pts[::3]:                           # sassolini e grana della terra
            for _ in range(3):
                px, py = round(x + rng.uniform(-r, r) * 0.7), round(y + rng.uniform(-r, r) * 0.7)
                if rng.random() < 0.3:
                    pygame.draw.ellipse(surf, _C_STONE_DK, (px, py + 1, 6, 4))
                    pygame.draw.ellipse(surf, _C_STONE, (px, py, 6, 3))
                else:
                    pygame.draw.rect(surf, _shade(_C_PATH, rng.randint(-14, 10)), (px, py, 2, 2))
        return surf

    def _render_vignette(self) -> pygame.Surface:
        W, H = s.SCREEN_W, s.SCREEN_H
        surf = gfx.Surface((W, H), pygame.SRCALPHA)
        steps = 24
        for i in range(steps):              # bordi più scuri, centro luminoso
            a = int(85 * (1 - i / steps) ** 2)
            pygame.draw.rect(surf, (8, 14, 18, a), (i * 9, i * 6, W - i * 18, H - i * 12), 9)
        return surf

    @staticmethod
    def _cut_crown(ground: pygame.Surface, bx: int, by: int, r: int) -> dict:
        """Ritaglia la chioma di un albero dallo sfondo (cerchio sfumato): ridisegnata sopra
        al gatto quando ci passa dietro, così l'albero resta davanti."""
        cx, cy = bx, by - r
        size   = r * 2 + 8
        area   = pygame.Rect(cx - size // 2, cy - size // 2, size, size)
        clip   = area.clip(ground.get_rect())
        crown  = gfx.Surface(area.size, pygame.SRCALPHA)
        crown.blit(ground, (clip.x - area.x, clip.y - area.y), clip)
        mask = gfx.Surface(area.size, pygame.SRCALPHA)
        for rr in range(r + 4, 0, -1):                       # bordo morbido
            a = 255 if rr <= r - 4 else round(255 * (r + 4 - rr) / 8)
            pygame.draw.circle(mask, (255, 255, 255, a), (size // 2, size // 2), rr)
        crown.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        faded = crown.copy()
        faded.set_alpha(120)
        trunk_w = max(12, r // 3)
        return dict(surf=crown, faded=faded, base=(bx, by), offset=(bx - area.x, by - area.y),
                    r=r, trunk_w=trunk_w, crown=pygame.Rect(cx - r, cy - r, r * 2, r * 2), painted=True)

    def _make_tree(self, cx: int, cy: int, r: int) -> dict:
        rng      = random.Random(cx * 7 + cy)
        trunk_h  = int(r * 0.9)
        trunk_w  = max(10, r // 2)
        w, h     = r * 2 + 24, r * 2 + trunk_h + 16
        bx, by   = w // 2, h - 6                     # base del tronco nella superficie
        surf     = gfx.Surface((w, h), pygame.SRCALPHA)

        # Tronco con radici, chiaro a sinistra (luce dall'alto-sinistra)
        pygame.draw.polygon(surf, _C_TRUNK_DK, [(bx - trunk_w, by), (bx - trunk_w // 2, by - 8),
                                                (bx + trunk_w // 2, by - 8), (bx + trunk_w, by)])
        pygame.draw.rect(surf, _C_TRUNK, (bx - trunk_w // 2, by - trunk_h, trunk_w, trunk_h))
        pygame.draw.rect(surf, _C_TRUNK_DK, (bx + trunk_w // 6, by - trunk_h, trunk_w // 3 + 1, trunk_h))
        pygame.draw.line(surf, _shade(_C_TRUNK, 24), (bx - trunk_w // 2 + 1, by - trunk_h), (bx - trunk_w // 2 + 1, by - 2))

        # Chioma a strati: contorno, ombra in basso a destra, mezzo tono, luce in alto a sinistra
        ccx, ccy = bx, by - trunk_h - int(r * 0.55)
        blobs = [(-0.55, 0.25, 0.68), (0.55, 0.25, 0.68), (0.0, -0.1, 1.0), (-0.3, -0.45, 0.62), (0.35, -0.4, 0.6)]
        for dx, dy, k in blobs:
            pygame.draw.circle(surf, (20, 40, 18), (ccx + int(dx * r), ccy + int(dy * r)), int(k * r) + 2)
        for dx, dy, k in blobs:
            pygame.draw.circle(surf, _C_LEAF_DK, (ccx + int(dx * r), ccy + int(dy * r)), int(k * r))
        pygame.draw.circle(surf, _C_LEAF, (ccx - int(r * 0.15), ccy - int(r * 0.2)), int(r * 0.78))
        pygame.draw.circle(surf, _C_LEAF, (ccx - int(r * 0.45), ccy + int(r * 0.05)), int(r * 0.5))
        pygame.draw.circle(surf, _C_LEAF_LT, (ccx - int(r * 0.35), ccy - int(r * 0.42)), int(r * 0.42))
        for _ in range(int(r * 1.4)):                     # ciuffi di foglie
            a, d = rng.uniform(0, math.tau), rng.uniform(0, r * 0.9)
            x, y = ccx + int(math.cos(a) * d), ccy + int(math.sin(a) * d * 0.9)
            lit = (x - ccx) + (y - ccy) < 0
            pygame.draw.circle(surf, _shade(_C_LEAF_LT if lit else _C_LEAF_DK, rng.randint(-8, 8)), (x, y), rng.randint(2, 4))
        faded = surf.copy()
        faded.set_alpha(115)                             # quando il gatto è dietro la chioma
        base  = (cx, cy + int(r * 1.4))
        crown = pygame.Rect(base[0] - bx, base[1] - by, w, by - 6)
        return dict(surf=surf, faded=faded, base=base, offset=(bx, by), r=r, trunk_w=trunk_w, crown=crown)

    @staticmethod
    def _npc_anims(n: dict):
        """Sprite 3D dell'NPC (tools/render_player_sprites.py --idle), se c'è il modello.
        Restituisce (cicli da fermo per direzione, distanza centro→piedi) o None."""
        loops = AssetManager.get().npc_loops(n["model"]) if n.get("model") else None
        if not loops:
            return None
        feet = AssetManager.sprite_meta(n["model"]).get("ground_px")
        if feet is None:                                     # stima: fondo della sagoma vista da sud
            frame = loops[len(loops) // 4][0]
            feet  = frame.get_bounding_rect(min_alpha=40).bottom - frame.get_height() // 2
        return loops, round(feet)

    def _make_npc(self, n: dict) -> pygame.Surface:
        """Gatto in piedi con la veste del suo mestiere; piedi in basso al centro."""
        w, h  = 64, 96
        surf  = gfx.Surface((w, h), pygame.SRCALPHA)
        cx, fy = w // 2, h - 4
        fur, robe = n["fur"], n["robe"]

        # Veste (trapezio), metà destra in ombra, orlo scuro
        pygame.draw.polygon(surf, robe, [(cx - 11, fy - 40), (cx + 11, fy - 40), (cx + 17, fy), (cx - 17, fy)])
        pygame.draw.polygon(surf, _shade(robe, -30), [(cx + 2, fy - 40), (cx + 11, fy - 40), (cx + 17, fy), (cx + 4, fy)])
        pygame.draw.rect(surf, _shade(robe, -45), (cx - 17, fy - 5, 34, 5))
        pygame.draw.circle(surf, _shade(robe, 10), (cx - 13, fy - 30), 5)       # maniche
        pygame.draw.circle(surf, _shade(robe, -25), (cx + 13, fy - 30), 5)
        pygame.draw.circle(surf, fur, (cx - 14, fy - 25), 3)                    # zampe
        pygame.draw.circle(surf, fur, (cx + 14, fy - 25), 3)

        # Testa di gatto
        hx, hy = cx, fy - 52
        for side in (-1, 1):
            pygame.draw.polygon(surf, fur, [(hx + side * 4, hy - 8), (hx + side * 13, hy - 19), (hx + side * 12, hy - 3)])
            pygame.draw.polygon(surf, (220, 140, 150), [(hx + side * 6, hy - 8), (hx + side * 11, hy - 15), (hx + side * 10, hy - 5)])
        pygame.draw.circle(surf, fur, (hx, hy), 12)
        pygame.draw.circle(surf, _shade(fur, -25), (hx + 4, hy + 3), 8)
        pygame.draw.circle(surf, fur, (hx - 1, hy), 10)
        for side in (-1, 1):
            pygame.draw.ellipse(surf, n["eyes"], (hx + side * 5 - 3, hy - 4, 6, 7))
            pygame.draw.ellipse(surf, (16, 14, 18), (hx + side * 5 - 1, hy - 3, 2, 5))
            pygame.draw.line(surf, (230, 226, 220), (hx + side * 6, hy + 4), (hx + side * 16, hy + 2))
            pygame.draw.line(surf, (230, 226, 220), (hx + side * 6, hy + 5), (hx + side * 16, hy + 7))
        pygame.draw.circle(surf, (220, 120, 140), (hx, hy + 4), 2)

        if n["tag"] == "spell":          # cappello a punta con stelle + bastone
            pygame.draw.ellipse(surf, _shade(robe, -35), (hx - 15, hy - 14, 30, 8))
            pygame.draw.polygon(surf, _shade(robe, -20), [(hx - 10, hy - 11), (hx + 10, hy - 11), (hx + 4, hy - 38), (hx - 1, hy - 40)])
            pygame.draw.polygon(surf, _shade(robe, -45), [(hx + 2, hy - 11), (hx + 10, hy - 11), (hx + 4, hy - 38)])
            for sx, sy in ((-4, -20), (2, -29), (5, -16)):
                pygame.draw.circle(surf, (250, 220, 90), (hx + sx, hy + sy), 1)
            pygame.draw.line(surf, (110, 76, 44), (cx + 22, fy), (cx + 22, fy - 60), 3)
        elif n["tag"] == "stats":        # occhialoni da alchimista + cintura con fiale
            for side in (-1, 1):
                pygame.draw.circle(surf, (180, 140, 60), (hx + side * 5, hy - 9), 4)
                pygame.draw.circle(surf, (150, 210, 220), (hx + side * 5, hy - 9), 2)
            pygame.draw.rect(surf, (90, 60, 36), (cx - 14, fy - 22, 28, 4))
            for vx_, vc in ((-8, (200, 70, 70)), (0, (80, 200, 120)), (8, (90, 130, 230))):
                pygame.draw.rect(surf, vc, (cx + vx_ - 2, fy - 20, 4, 6))
        else:                            # barba lunga + bastone da passeggio
            pygame.draw.polygon(surf, (236, 232, 226), [(hx - 7, hy + 6), (hx + 7, hy + 6), (hx, hy + 22)])
            pygame.draw.line(surf, (96, 70, 44), (cx - 21, fy), (cx - 19, fy - 44), 3)
            pygame.draw.circle(surf, (96, 70, 44), (cx - 17, fy - 45), 4, 2)
        return surf

    def _make_entrance(self) -> pygame.Surface:
        """Collina rocciosa con arco di pietra e gradini che scendono nel buio."""
        w, h = 220, 150
        surf = gfx.Surface((w, h), pygame.SRCALPHA)
        rng  = random.Random(21)
        cx, by = w // 2, h - 8                           # base dell'ingresso

        # Collina: rocce sovrapposte, più scure in basso, con muschio ed erba in cima
        for _ in range(26):
            x = cx + rng.randint(-92, 92)
            y = by - rng.randint(16, 70) + abs(x - cx) // 3
            rr = rng.randint(18, 32)
            pygame.draw.circle(surf, _C_STONE_DK, (x, y), rr)
            pygame.draw.circle(surf, _shade(_C_STONE, rng.randint(-20, 0)), (x - 3, y - 4), rr - 5)
            pygame.draw.circle(surf, _shade(_C_STONE_LT, rng.randint(-20, 0)), (x - 7, y - 9), rr // 3)
        for _ in range(40):
            x = cx + rng.randint(-80, 80)
            y = by - 78 + abs(x - cx) // 2 + rng.randint(-6, 6)
            pygame.draw.circle(surf, rng.choice([_C_LEAF, _C_LEAF_LT, _C_GRASS]), (x, y), rng.randint(3, 7))

        # Apertura: buio con gradini che scendono
        ow, oh = 64, 58
        ox, oy = cx - ow // 2, by - oh
        pygame.draw.rect(surf, _C_CAVE, (ox, oy + 14, ow, oh - 14))
        pygame.draw.ellipse(surf, _C_CAVE, (ox, oy, ow, 30))
        for i, sy in enumerate(range(by - 6, oy + 18, -8)):
            shade = max(0, 70 - i * 14)
            pygame.draw.rect(surf, (shade, shade - 4 if shade > 4 else 0, shade + 6), (ox + 4 + i * 3, sy, ow - 8 - i * 6, 3))

        # Arco di pietre attorno all'apertura + pilastri con faccia frontale
        for k in range(9):
            a = math.pi + k * math.pi / 8
            x = cx + int(math.cos(a) * (ow // 2 + 6))
            y = oy + 15 + int(math.sin(a) * 21)
            pygame.draw.rect(surf, _C_STONE_DK, (x - 8, y - 6, 16, 13), border_radius=3)
            pygame.draw.rect(surf, _C_STONE, (x - 7, y - 6, 14, 10), border_radius=3)
        for side in (-1, 1):
            px = cx + side * (ow // 2 + 6) - 9
            pygame.draw.rect(surf, _C_STONE_DK, (px, oy + 14, 18, by - oy - 14))
            pygame.draw.rect(surf, _C_STONE, (px, oy + 14, 12 if side < 0 else 18, by - oy - 14))
            for yy in range(oy + 22, by, 12):
                pygame.draw.line(surf, _C_STONE_DK, (px, yy), (px + 17, yy))
            pygame.draw.rect(surf, (60, 46, 30), (px + 5, oy + 26, 8, 6))           # supporto torcia
        return surf

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, player):
        assets = AssetManager.get()
        t      = pygame.time.get_ticks() / 1000.0
        surface.blit(self._ground, (0, 0))

        # Ombre a terra (sole dall'alto-sinistra → ombre verso il basso a destra)
        for tree in self._trees if not self._painted else ():
            bx, by, r = *tree["base"], tree["r"]
            sh = assets.shadow(r * 2 + 18, int(r * 0.8))
            surface.blit(sh, sh.get_rect(center=(bx + int(r * 0.45), by)))
        for n in self._npcs:
            sh = assets.shadow(40, 13)
            surface.blit(sh, sh.get_rect(center=(n["pos"][0] + 3, n["pos"][1] + _NPC_FEET)))
        k  = player.jump_height / s.PLAYER_DODGE_JUMP                 # in aria: ombra più piccola
        sh = assets.shadow(round(38 - 12 * k), round(13 - 4 * k))
        surface.blit(sh, sh.get_rect(center=(round(player.pos.x), player.rect.bottom - 3)))

        # Oggetti con altezza ordinati per Y della base: il gatto passa dietro alberi e NPC
        ex, ey = ENTRANCE_POS
        drawables = [(ey + 30, lambda: (self._draw_torches(surface, t) if self._painted
                                        else self._draw_entrance(surface, t)))]
        for tree in self._trees:
            drawables.append((tree["base"][1], lambda tr=tree: self._draw_tree(surface, tr, player)))
        for i, n in enumerate(self._npcs):
            drawables.append((n["pos"][1] + _NPC_FEET, lambda n=n, i=i: self._draw_npc(surface, n, t, i, player)))
        if self.gate_active:
            drawables.append((GATE_POS[1] + 18, lambda: self._draw_gate(surface, t)))
        drawables.append((player.rect.bottom, lambda: player.draw(surface)))
        drawables.sort(key=lambda d: d[0])
        for _, fn in drawables:
            fn()

        # Lucciole e vignettatura
        for x0, y0, ph, sp in self._fireflies:
            x = x0 + 30 * math.sin(t * sp + ph)
            y = y0 + 18 * math.sin(t * sp * 1.7 + ph * 2)
            if math.sin(t * 2.2 + ph * 3) > -0.2:
                surface.blit(self._firefly, (round(x) - 9, round(y) - 9), special_flags=pygame.BLEND_RGB_ADD)
        surface.blit(self._vignette, (0, 0))

        self._draw_labels(surface, player.pos)

    def _draw_tree(self, surface, tree, player):
        bx, by = tree["base"]
        ox, oy = tree["offset"]
        cat = pygame.Rect(0, 0, 44, 56)
        cat.midbottom = player.rect.midbottom
        behind = player.rect.bottom < by and cat.colliderect(tree["crown"])
        if tree.get("painted") and not behind:
            return                                           # già nello sfondo
        surface.blit(tree["faded" if behind else "surf"], (bx - ox, by - oy))

    def _draw_npc(self, surface, n, t, i, player=None):
        vx, vy = n["pos"]
        fx, fy = vx, vy + _NPC_FEET
        if n["anims"]:                                       # modello 3D: si gira piano verso il gatto
            loops, feet = n["anims"]
            target = 90.0                                    # a riposo guarda in basso (sud)
            if player is not None:
                to_p = player.pos - pygame.math.Vector2(vx, vy)
                if 0 < to_p.length() < s.NPC_LOOK_RANGE:
                    target = math.degrees(math.atan2(to_p.y, to_p.x))
            angle = n.get("angle", 90.0)
            dt    = min(0.1, max(0.0, t - n.get("last_t", t)))
            diff  = (target - angle + 180) % 360 - 180       # verso più corto
            step  = s.NPC_TURN_SPEED * dt
            angle = target if abs(diff) <= step else angle + math.copysign(step, diff)
            n["angle"], n["last_t"] = angle % 360, t
            frames = loops[round(angle / (360 / len(loops))) % len(loops)]
            frame  = frames[int(t * 8 + i * 5) % len(frames)]
            surface.blit(frame, frame.get_rect(center=(fx, fy - feet)))
            if n["tag"] == "spell":                          # scintille magiche che salgono
                for k in range(5):
                    ph = (t * 0.5 + k / 5) % 1.0
                    sx = fx + round(math.sin(t * 1.3 + k * 2.1) * 22)
                    sy = fy - 20 - round(ph * 60)
                    c  = round(255 * (1 - ph))
                    pygame.draw.circle(surface, (min(255, 150 + c // 3), 110 + c // 3, 255), (sx, sy), 2 if ph < 0.6 else 1)
                return
        else:
            bob = round(math.sin(t * 2.0 + i * 1.7))         # respiro
            spr = n["sprite"]
            surface.blit(spr, (fx - spr.get_width() // 2, fy - spr.get_height() + 4 + bob))
        if n["tag"] == "spell":                              # sfera luminosa sul bastone
            ox, oy = fx + 22, fy - 62 + bob
            pulse = 1 + 0.15 * math.sin(t * 4)
            surface.blit(self._orb_glow, (ox - 22, oy - 22), special_flags=pygame.BLEND_RGB_ADD)
            pygame.draw.circle(surface, (200, 160, 255), (ox, oy), round(5 * pulse))
            pygame.draw.circle(surface, (250, 240, 255), (ox - 1, oy - 1), 2)
        elif n["tag"] == "stats":                            # calderone che ribolle
            cx, cy = fx + (44 if n["anims"] else 34), fy - 4
            pygame.draw.ellipse(surface, (30, 28, 34), (cx - 16, cy - 14, 32, 22))
            pygame.draw.ellipse(surface, (48, 46, 54), (cx - 16, cy - 16, 32, 20))
            pygame.draw.ellipse(surface, (80, 200, 110), (cx - 12, cy - 15, 24, 9))
            for k in range(3):
                ph = (t * 1.3 + k * 0.33) % 1.0
                pygame.draw.circle(surface, (150, 240, 160), (cx - 6 + k * 6, round(cy - 12 - ph * 16)), max(1, round(3 * (1 - ph))))

    def _draw_entrance(self, surface, t):
        ex, ey = ENTRANCE_POS
        w, h = self._entrance.get_size()
        left, top = ex - w // 2, ey + 30 - (h - 8)
        surface.blit(self._entrance, (left, top))
        for side in (-1, 1):                                 # torce che tremolano
            tx = ex + side * 38
            ty = top + (h - 8) - 58 + 22
            flick = 0.85 + 0.15 * math.sin(t * 17 + side) * math.sin(t * 7.3)
            g = self._torch_glow
            gs = pygame.transform.smoothscale(g, (int(g.get_width() * flick), int(g.get_height() * flick)))
            surface.blit(gs, gs.get_rect(center=(tx, ty)), special_flags=pygame.BLEND_RGB_ADD)
            fh = round(9 * flick)
            pygame.draw.polygon(surface, (240, 120, 40), [(tx - 4, ty), (tx + 4, ty), (tx + round(math.sin(t * 13) * 2), ty - fh - 4)])
            pygame.draw.polygon(surface, (255, 220, 110), [(tx - 2, ty), (tx + 2, ty), (tx, ty - fh)])

    def _draw_torches(self, surface, t):
        """Sfondo dipinto: solo la luce tremolante delle torce della grotta."""
        for k, (tx, ty) in enumerate(_BG_TORCHES):
            flick = 0.85 + 0.15 * math.sin(t * 17 + k) * math.sin(t * 7.3)
            g  = self._torch_glow_soft
            gs = pygame.transform.smoothscale(g, (int(g.get_width() * flick), int(g.get_height() * flick)))
            surface.blit(gs, gs.get_rect(center=(tx, ty)), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_gate(self, surface, t):
        gx, gy = GATE_POS
        base_y = gy + 18
        if not self._painted:                                # piattaforma di pietra con spessore
            pygame.draw.ellipse(surface, _C_STONE_DK, (gx - 34, base_y - 8, 68, 22))
            pygame.draw.ellipse(surface, _C_STONE, (gx - 34, base_y - 14, 68, 22))
            pygame.draw.ellipse(surface, _C_STONE_LT, (gx - 26, base_y - 11, 52, 15), 2)
        # Anello magico sospeso che ruota
        ring_w = max(6, round(40 * abs(math.cos(t * 1.6))))
        cy = gy - 10 + round(3 * math.sin(t * 2))
        surface.blit(self._orb_glow, (gx - 22, cy - 22), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.ellipse(surface, (120, 55, 190), (gx - ring_w // 2, cy - 26, ring_w, 52), 4)
        pygame.draw.ellipse(surface, (200, 160, 255), (gx - ring_w // 2 + 2, cy - 24, max(2, ring_w - 4), 48), 1)
        for k in range(5):                                   # scintille che salgono
            ph = (t * 0.7 + k / 5) % 1.0
            x = gx + round(math.sin(k * 2.1 + t) * 18)
            pygame.draw.circle(surface, (220, 200, 255), (x, round(base_y - 8 - ph * 50)), 1 if ph > 0.5 else 2)

    def _draw_labels(self, surface, player_pos):
        """Nomi e suggerimenti sopra a tutto, sempre leggibili."""
        px, py = float(player_pos[0]), float(player_pos[1])

        def near(x, y, radius):
            return (px - x) ** 2 + (py - y) ** 2 <= radius ** 2

        pad  = InputManager.get()
        font = AssetManager.get().ui_font(16)       # con il controller: font coi simboli

        def text(msg, color, **pos):
            msg = pad.label(msg, msg.replace("[E]", "[{A}]"))
            lbl = font.render(msg, True, color)
            rect = lbl.get_rect(**pos)
            shadow = font.render(msg, True, (10, 12, 10))
            surface.blit(shadow, rect.move(1, 1))
            surface.blit(lbl, rect)

        for n in self._npcs:
            vx, vy = n["pos"]
            text(n["name"], (236, 228, 205), centerx=vx, bottom=vy - 58)
            if near(vx, vy, s.VENDOR_INTERACT_RADIUS):
                text(n["hint"], (250, 240, 130), centerx=vx, top=vy + _NPC_FEET + 8)
        ex, ey = ENTRANCE_POS
        text("Dungeon", (205, 198, 186), centerx=ex, bottom=ey - 66)
        if near(ex, ey, s.ENTRANCE_INTERACT_RADIUS):
            text("[E] Entra nel dungeon", (250, 240, 130), centerx=ex, top=ey + 38)
        if self.gate_active:
            gx, gy = GATE_POS
            text("Gate Recall", (196, 160, 240), centerx=gx, bottom=gy - 40)
            if near(gx, gy, s.ENTRANCE_INTERACT_RADIUS):
                text("[E] Torna dove eri", (250, 240, 130), centerx=gx, top=gy + 36)
