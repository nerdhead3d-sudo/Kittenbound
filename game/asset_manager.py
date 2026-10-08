import json
import random
import pygame
from pathlib import Path
from game import settings as s
from game import gfx

# Cerca i PNG in assets/sprites/ nella directory del progetto.
# Se il file non esiste si cade automaticamente sul placeholder procedurale.
_SPRITES_DIR = Path(__file__).resolve().parent.parent / "assets" / "sprites"


class AssetManager:
    """Singleton. Carica sprite da PNG o genera placeholder procedurali.

    Convenzione nomi file (tutti in assets/sprites/):
        player.png
        enemy_mouse_warrior.png  enemy_mouse_archer.png
        enemy_mouse_mage.png     enemy_skeleton.png
        proj_player.png          proj_enemy.png
        loot_coin.png            loot_hp.png   loot_mp.png
    """

    _instance = None

    @classmethod
    def get(cls) -> "AssetManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._cache: dict = {}

    # ── PNG loader ────────────────────────────────────────────────────────────

    def _load_png(self, key: str) -> "pygame.Surface | None":
        """Carica assets/sprites/<key>.png; restituisce None se assente o corrotto.
        In HD (gfx.K > 1) preferisce <key>@2x.png, generato a doppia risoluzione: la dimensione
        logica dello sprite resta quella normale, ma viene disegnato con il doppio dei dettagli."""
        for name, img_scale in ((f"{key}@2x", 2), (key, 1)) if gfx.K > 1 else ((key, 1), (f"{key}@2x", 2)):
            path = _SPRITES_DIR / f"{name}.png"
            if not path.exists():
                continue
            try:
                return gfx.from_image(pygame.image.load(str(path)).convert_alpha(), img_scale)
            except pygame.error:
                return None
        return None

    @staticmethod
    def image_path(key: str) -> Path:
        return _SPRITES_DIR / f"{key}.png"

    # ── Player ────────────────────────────────────────────────────────────────

    def player_sprite(self) -> pygame.Surface:
        key = "player"
        if key not in self._cache:
            self._cache[key] = self._load_png(key) or self._make_player()
        return self._cache[key]

    def player_animations(self) -> "dict[str, list[list[pygame.Surface]]] | None":
        return self.animations("player")

    def enemy_animations(self, enemy_type: str) -> "dict[str, list[list[pygame.Surface]]] | None":
        return self.animations(f"enemy_{enemy_type}")

    def animations(self, prefix: str) -> "dict[str, list[list[pygame.Surface]]] | None":
        """Animazioni per direzione (0=E, poi in senso orario ogni 45°):
            {"idle": [[frame]]*8, "walk": [[frame, ...]]*8, "attack": [[frame, ...]]*8,
             "idle_loop": [[frame, ...]]*8}   (idle_loop: NPC fermi, <prefix>_idle_<d>.png)
        Generate da tools/render_player_sprites.py e tools/render_enemy_sprites.py:
        <prefix>_<d>.png, <prefix>_walk_<d>.png, <prefix>_attack_<d>.png ("walk"/"attack"
        sono strip orizzontali di frame quadrati). None se mancano gli sprite di base."""
        key = f"anims_{prefix}"
        if key not in self._cache:
            idle = [self._load_png(f"{prefix}_{i}") for i in range(8)]
            if not all(idle):
                self._cache[key] = None
                return None
            anims = {"idle": [[img] for img in idle]}
            for name, key_name in (("walk", "walk"), ("attack", "attack"), ("idle", "idle_loop")):
                strips = [self._load_png(f"{prefix}_{name}_{i}") for i in range(8)]
                if all(strips):
                    anims[key_name] = [self._split_strip(strip) for strip in strips]
            self._cache[key] = anims
        return self._cache[key]

    def npc_loops(self, prefix: str) -> "list[list[pygame.Surface]] | None":
        """Cicli da fermo di un NPC in N direzioni (<prefix>_idle_<d>.png, d = 0..N-1,
        0 = est in senso orario), generati con render_player_sprites.py --idle."""
        key = f"npc_{prefix}"
        if key not in self._cache:
            loops, d = [], 0
            while (strip := self._load_png(f"{prefix}_idle_{d}")) is not None:
                loops.append(self._split_strip(strip))
                d += 1
            self._cache[key] = loops or None
        return self._cache[key]

    @staticmethod
    def sprite_meta(prefix: str) -> dict:
        """Dati extra di uno sprite (<prefix>_meta.json), es. il punto d'appoggio a terra."""
        path = _SPRITES_DIR / f"{prefix}_meta.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def boulder(self) -> pygame.Surface:
        key = "boulder"
        if key not in self._cache:
            img = self._load_png(key)
            if img is None:
                img = gfx.Surface((46, 40), pygame.SRCALPHA)
                rng = random.Random(9)
                pygame.draw.ellipse(img, (54, 50, 46), (1, 4, 44, 35))
                pygame.draw.ellipse(img, (104, 98, 90), (3, 3, 38, 31))
                pygame.draw.ellipse(img, (138, 132, 122), (8, 5, 20, 14))
                for _ in range(5):                                 # crepe
                    x0, y0 = rng.randint(10, 34), rng.randint(10, 30)
                    pygame.draw.line(img, (60, 56, 52), (x0, y0), (x0 + rng.randint(-7, 7), y0 + rng.randint(-5, 5)), 2)
                pygame.draw.ellipse(img, (40, 36, 34), (1, 4, 44, 35), 2)
            self._cache[key] = img
        return self._cache[key]

    def fx_frames(self, name: str) -> "list[pygame.Surface] | None":
        """Frame di un oggetto/effetto (fx_<name>.png, strip orizzontale) generati da
        tools/render_prop_sprites.py: frame i = direzione i * 360/N gradi, perno al centro."""
        key = f"fx_{name}"
        if key not in self._cache:
            strip = self._load_png(key)
            self._cache[key] = self._split_strip(strip) if strip else None
        return self._cache[key]

    def tinted(self, frame: pygame.Surface, color: tuple) -> pygame.Surface:
        """Copia del frame moltiplicata per un colore (es. boss in furia o stordito)."""
        key = ("tint", id(frame), color)
        if key not in self._cache:
            surf = frame.copy()
            surf.fill(color, special_flags=pygame.BLEND_RGB_MULT)
            self._cache[key] = surf
        return self._cache[key]

    @staticmethod
    def _split_strip(strip: pygame.Surface) -> list[pygame.Surface]:
        size = strip.get_height()
        return [strip.subsurface((x, 0, size, size)) for x in range(0, strip.get_width(), size)]

    def _make_player(self) -> pygame.Surface:
        size = s.PLAYER_RADIUS * 2 + 8
        surf = gfx.Surface((size, size), pygame.SRCALPHA)
        cx, cy = size // 2, size // 2
        r = s.PLAYER_RADIUS

        pygame.draw.circle(surf, s.C_PLAYER_ROBE, (cx, cy + 4), r)
        pygame.draw.circle(surf, s.C_PLAYER, (cx, cy - 2), r - 4)
        ear_color = s.C_PLAYER
        pygame.draw.polygon(surf, ear_color, [
            (cx - 7, cy - r + 2),
            (cx - 11, cy - r - 6),
            (cx - 3,  cy - r - 2),
        ])
        pygame.draw.polygon(surf, ear_color, [
            (cx + 7, cy - r + 2),
            (cx + 11, cy - r - 6),
            (cx + 3,  cy - r - 2),
        ])
        pygame.draw.polygon(surf, (60, 40, 50), [
            (cx - 7,  cy - r + 3),
            (cx - 10, cy - r - 4),
            (cx - 4,  cy - r - 1),
        ])
        pygame.draw.polygon(surf, (60, 40, 50), [
            (cx + 7,  cy - r + 3),
            (cx + 10, cy - r - 4),
            (cx + 4,  cy - r - 1),
        ])
        pygame.draw.circle(surf, s.C_PLAYER_EYE, (cx - 5, cy - 4), 4)
        pygame.draw.circle(surf, s.C_PLAYER_EYE, (cx + 5, cy - 4), 4)
        pygame.draw.circle(surf, (10, 10, 10), (cx - 5, cy - 4), 2)
        pygame.draw.circle(surf, (10, 10, 10), (cx + 5, cy - 4), 2)
        pygame.draw.circle(surf, (120, 255, 160), (cx + r - 2, cy + r - 4), 4)
        pygame.draw.circle(surf, (200, 255, 220), (cx + r - 2, cy + r - 4), 2)
        return surf

    # ── Nemici ────────────────────────────────────────────────────────────────

    def enemy_sprite(self, enemy_type: str) -> pygame.Surface:
        key = f"enemy_{enemy_type}"
        if key not in self._cache:
            self._cache[key] = self._load_png(key) or self._make_enemy(enemy_type)
        return self._cache[key]

    def _make_enemy(self, enemy_type: str) -> pygame.Surface:
        color_map = {
            "mouse_warrior": s.C_MOUSE_WARRIOR,
            "mouse_archer":  s.C_MOUSE_ARCHER,
            "mouse_mage":    s.C_MOUSE_MAGE,
            "mouse_lancer":  s.C_MOUSE_LANCER,
            "mouse_slinger": (200, 120, 50),
            "skeleton":      s.C_SKELETON,
        }
        color = color_map.get(enemy_type, (150, 150, 150))
        size = 36
        surf = gfx.Surface((size, size), pygame.SRCALPHA)
        cx, cy = size // 2, size // 2

        pygame.draw.circle(surf, color, (cx, cy), 14)
        pygame.draw.circle(surf, (0, 0, 0), (cx, cy), 14, 2)
        ear_r = 6
        pygame.draw.circle(surf, color, (cx - 12, cy - 10), ear_r)
        pygame.draw.circle(surf, color, (cx + 12, cy - 10), ear_r)
        pygame.draw.circle(surf, (0, 0, 0), (cx - 12, cy - 10), ear_r, 1)
        pygame.draw.circle(surf, (0, 0, 0), (cx + 12, cy - 10), ear_r, 1)
        pygame.draw.circle(surf, (220, 60, 60), (cx - 4, cy - 2), 3)
        pygame.draw.circle(surf, (220, 60, 60), (cx + 4, cy - 2), 3)

        if enemy_type == "mouse_warrior":
            pygame.draw.line(surf, (200, 200, 200), (cx - 6, cy + 8), (cx + 6, cy + 2), 2)
        elif enemy_type == "mouse_archer":
            pygame.draw.arc(surf, (160, 120, 60),
                            pygame.Rect(cx - 8, cy + 2, 10, 10), 0, 3.14, 2)
        elif enemy_type == "mouse_mage":
            pygame.draw.circle(surf, (150, 150, 255), (cx, cy + 8), 4)
        elif enemy_type == "skeleton":
            pygame.draw.line(surf, (180, 180, 160), (cx - 5, cy + 6), (cx + 5, cy + 10), 2)
            pygame.draw.line(surf, (180, 180, 160), (cx + 5, cy + 6), (cx - 5, cy + 10), 2)

        return surf

    # ── Proiettili ────────────────────────────────────────────────────────────

    def projectile_sprite(self, owner: str = "player") -> pygame.Surface:
        key = f"proj_{owner}"
        if key not in self._cache:
            self._cache[key] = self._load_png(key) or self._make_projectile(owner)
        return self._cache[key]

    def _make_projectile(self, owner: str) -> pygame.Surface:
        r = s.SPELL_FIREBALL_RADIUS
        size = r * 2 + 4
        surf = gfx.Surface((size, size), pygame.SRCALPHA)
        color = s.C_PROJ_PLAYER if owner == "player" else s.C_PROJ_ENEMY
        cx = size // 2
        pygame.draw.circle(surf, (*color[:3], 80), (cx, cx), r + 2)
        pygame.draw.circle(surf, color, (cx, cx), r)
        pygame.draw.circle(surf, (255, 255, 255), (cx - 1, cx - 1), max(1, r // 3))
        return surf

    # ── Loot ──────────────────────────────────────────────────────────────────

    def loot_sprite(self, loot_type: str) -> pygame.Surface:
        key = f"loot_{loot_type}"
        if key not in self._cache:
            self._cache[key] = self._load_png(key) or self._make_loot(loot_type)
        return self._cache[key]

    def _make_loot(self, loot_type: str) -> pygame.Surface:
        r = s.LOOT_RADIUS
        size = r * 2 + 2
        surf = gfx.Surface((size, size), pygame.SRCALPHA)
        cx = size // 2
        color_map = {
            "coin": s.C_COIN,
            "hp":   s.C_POTION_HP,
            "mp":   s.C_POTION_ENERGY,
        }
        color = color_map.get(loot_type, (200, 200, 200))
        pygame.draw.circle(surf, color, (cx, cx), r)
        pygame.draw.circle(surf, (255, 255, 255), (cx, cx), r, 1)
        return surf

    # ── Chest ─────────────────────────────────────────────────────────────────

    def chest_sprite(self) -> pygame.Surface:
        key = "chest"
        if key not in self._cache:
            self._cache[key] = self._load_png(key) or self._make_chest()
        return self._cache[key]

    def _make_chest(self) -> pygame.Surface:
        size = 32
        surf = gfx.Surface((size, size), pygame.SRCALPHA)
        # Corpo
        pygame.draw.rect(surf, (120, 80, 40),  (3, 14, 26, 15), border_radius=2)
        # Coperchio
        pygame.draw.rect(surf, (150, 100, 50), (3, 6, 26, 10),  border_radius=3)
        # Bordi dorati
        pygame.draw.rect(surf, (210, 170, 50), (3, 6, 26, 10),  1, border_radius=3)
        pygame.draw.rect(surf, (210, 170, 50), (3, 14, 26, 15), 1, border_radius=2)
        # Cerniera orizzontale
        pygame.draw.rect(surf, (210, 170, 50), (3, 16, 26, 2))
        # Serratura
        pygame.draw.circle(surf, (230, 190, 55), (16, 22), 3)
        pygame.draw.circle(surf, (160, 120, 30), (16, 22), 3, 1)
        return surf

    # ── Finto 3D: muri, ombre, luce ───────────────────────────────────────────

    def _tile_set(self, prefix: str) -> list:
        """Tile ritagliate dalla stanza dipinta (tools/slice_dungeon_tiles.py): <prefix>_0, _1, ..."""
        key = f"set_{prefix}"
        if key not in self._cache:
            tiles, i = [], 0
            while (img := self._load_png(f"{prefix}_{i}")) is not None:
                tiles.append(img)
                i += 1
            self._cache[key] = tiles
        return self._cache[key]

    # Tileset del bioma: "" = dungeon del Bosco, "sewer_" = Fogne (tools/slice_sewer_tiles.py)
    tileset = ""

    @classmethod
    def set_tileset(cls, prefix: str):
        """Cambia i pezzi usati per pavimento e muri delle stanze create da qui in poi."""
        cls.tileset = prefix

    def floor_tiles(self) -> "tuple[list, list]":
        """Piastrelle scure e chiare (il pavimento dipinto è a scacchiera)."""
        tp = self.tileset
        dark, light = self._tile_set(f"{tp}floor_dark"), self._tile_set(f"{tp}floor_light")
        if not dark or not light:                       # tileset mancante: quello del dungeon
            dark, light = self._tile_set("floor_dark"), self._tile_set("floor_light")
        return dark, light

    def water_tiles(self) -> "tuple[list, list, list, list]":
        """Acqua del canale orizzontale e di quello verticale (i primi 12 pezzi tagliati
        vengono dal canale orizzontale del dipinto, gli altri da quello verticale) e
        grate-ponte (sul canale orizzontale, su quello verticale)."""
        water  = self._tile_set("sewer_water")
        grates = self._tile_set("sewer_channel_grate")
        return water[:12], water[12:] or water[:12], grates[:2], grates[2:]

    def wall_slabs(self) -> dict:
        """Blocchi del muro ritagliati dalla stanza dipinta, per tipo:
        "h1".."h3" orizzontali lunghi n tile, "v1".."v2" verticali alti n tile, "p" pilastri.
        Ogni voce: (cima, mattoni o None)."""
        tp  = self.tileset if self._tile_set(f"{self.tileset}slab_h1") else ""
        key = f"wall_slabs_{tp}"
        if key not in self._cache:
            slabs = {}
            for kind in ("h1", "h2", "h3", "v1", "v2", "p"):
                tops = self._tile_set(f"{tp}slab_{kind}")
                slabs[kind] = [(top, self._load_png(f"{tp}slab_{kind}_{i}_face")) for i, top in enumerate(tops)]
            self._cache[key] = slabs
        return self._cache[key]

    def torch(self) -> "tuple[pygame.Surface, dict] | None":
        """Torcia a muro ritagliata (con i bordi sfumati per fondersi col muro) e i suoi dati."""
        key = "torch"
        if key not in self._cache:
            img = self._load_png("torch")
            if img is not None:
                img = img.copy()
                w, h = img.get_size()
                k = w / 69                                # coordinate del ritaglio originale (69x103)
                # Solo la torcia (fiamma + supporto): il muro dietro è già illuminato d'arancio
                # nel dipinto e farebbe un rettangolo chiaro sulle nostre pietre.
                mask = gfx.Surface((w, h), pygame.SRCALPHA)
                for i in range(4, 0, -1):                 # bordi sfumati: dal largo al pieno
                    col = (255, 255, 255, 255 if i == 1 else round(255 * (4 - i) / 4))
                    g = i - 1
                    pygame.draw.ellipse(mask, col, ((22 - g) * k, (12 - g) * k, (24 + 2 * g) * k, (50 + 2 * g) * k))
                    pygame.draw.polygon(mask, col, [((20 - g) * k, 56 * k), ((48 + g) * k, 56 * k),
                                                    ((40 + g) * k, (98 + g) * k), ((28 - g) * k, (98 + g) * k)])
                img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                real = gfx.hi_surface(img)                # nella fiamma resta solo il fuoco vivo
                fy   = round(56 * k * real.get_height() / h)
                for y in range(fy):
                    for x in range(real.get_width()):
                        r, g, b, a = real.get_at((x, y))
                        if a and (r + g + b) / 3 < 150:
                            real.set_at((x, y), (r, g, b, round(a * max(0.0, ((r + g + b) / 3 - 115) / 35))))
                self._cache[key] = (img, self.sprite_meta("torch"))
            else:
                self._cache[key] = None
        return self._cache[key]

    def wall_top(self, variant: int = 0) -> pygame.Surface:
        tiles = self._tile_set("wall_top")
        if tiles:
            return tiles[variant % len(tiles)]
        key = "wall_top"
        if key not in self._cache:
            self._cache[key] = self._load_png(key) or self._make_wall_top()
        return self._cache[key]

    def _make_wall_top(self) -> pygame.Surface:
        T = s.TILE_SIZE
        surf = gfx.Surface((T, T))
        surf.fill(s.C_WALL_TOP)
        rng = random.Random(7)
        for _ in range(40):                                   # grana della pietra
            shade = rng.randint(-10, 10)
            c = tuple(max(0, min(255, v + shade)) for v in s.C_WALL_TOP)
            pygame.draw.rect(surf, c, (rng.randrange(T), rng.randrange(T), 3, 3))
        pygame.draw.line(surf, (110, 104, 122), (0, 0), (T - 1, 0))   # spigolo illuminato
        pygame.draw.line(surf, (40, 37, 46), (0, T - 1), (T - 1, T - 1))
        return surf

    def wall_face(self, variant: int = 0) -> pygame.Surface:
        tiles = self._tile_set("wall_face")
        if tiles:
            return tiles[variant % len(tiles)]
        key = f"wall_face_{variant % 2}"
        if key not in self._cache:
            self._cache[key] = self._load_png(key) or self._make_wall_face(variant % 2)
        return self._cache[key]

    def _make_wall_face(self, variant: int) -> pygame.Surface:
        """Faccia frontale in mattoni, più scura in basso (luce dall'alto)."""
        T, H = s.TILE_SIZE, s.WALL_HEIGHT
        surf = gfx.Surface((T, H))
        surf.fill(s.C_WALL_MORTAR)
        rng = random.Random(100 + variant)
        brick_h = 10
        for row, y in enumerate(range(0, H, brick_h)):
            offset = (row + variant) % 2 * 12
            for x in range(-offset, T, 24):
                shade = rng.randint(-8, 8) - row * 4
                c = tuple(max(0, min(255, v + shade)) for v in s.C_WALL_FACE)
                pygame.draw.rect(surf, c, (x + 1, y + 1, 22, brick_h - 2))
        grad = gfx.Surface((T, H), pygame.SRCALPHA)
        for y in range(H):
            pygame.draw.line(grad, (0, 0, 0, int(70 * y / H)), (0, y), (T, y))
        surf.blit(grad, (0, 0))
        return surf

    def shadow(self, width: int, height: int) -> pygame.Surface:
        """Ellisse morbida da mettere a terra sotto personaggi e oggetti."""
        key = f"shadow_{width}_{height}"
        if key not in self._cache:
            surf = gfx.Surface((width, height), pygame.SRCALPHA)
            steps = 6
            for i in range(steps):
                f = i / steps
                rect = pygame.Rect(0, 0, int(width * (1 - f * 0.5)), int(height * (1 - f * 0.5)))
                rect.center = (width // 2, height // 2)
                # draw sostituisce l'alpha: ellissi interne più scure → bordo sfumato
                pygame.draw.ellipse(surf, (0, 0, 0, int(s.SHADOW_ALPHA * (i + 1) / steps)), rect)
            self._cache[key] = surf
        return self._cache[key]

    def torch_glow(self) -> pygame.Surface:
        """Alone caldo delle torce a muro (da sommare: BLEND_RGB_ADD)."""
        key = "torch_glow"
        if key not in self._cache:
            r = 46
            surf = gfx.Surface((r * 2, r * 2))
            for rr in range(r, 0, -2):
                f = (1 - rr / r) ** 2
                pygame.draw.circle(surf, (round(150 * f), round(80 * f), round(25 * f)), (r, r), rr)
            self._cache[key] = surf
        return self._cache[key]

    def light_hole(self, radius: int) -> pygame.Surface:
        """Foro di luce nel buio: trasparenza 0 al centro, piena al bordo. Si applica allo
        strato del buio con BLEND_RGBA_MIN (luci vicine si sommano senza fare aloni scuri)."""
        key = f"light_hole_{radius}"
        if key not in self._cache:
            surf = gfx.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            surf.fill((255, 255, 255, 255))
            for r in range(radius, 0, -3):
                a = round(255 * (r / radius) ** 1.3)       # sfuma presto: si vede bene solo vicino
                pygame.draw.circle(surf, (255, 255, 255, a), (radius, radius), r)
            self._cache[key] = surf
        return self._cache[key]

    def warm_light(self, radius: int, strength: int) -> pygame.Surface:
        """Luce calda da sommare (BLEND_RGB_ADD): schiarisce attorno al gatto."""
        key = f"warm_light_{radius}_{strength}"
        if key not in self._cache:
            surf = gfx.Surface((radius * 2, radius * 2))
            for r in range(radius, 0, -3):
                f = (1 - r / radius) ** 2
                pygame.draw.circle(surf, (round(strength * f), round(strength * 0.8 * f), round(strength * 0.55 * f)),
                                   (radius, radius), r)
            self._cache[key] = surf
        return self._cache[key]

    def light_overlay(self) -> pygame.Surface:
        """Buio con un alone di luce al centro; grande 2x lo schermo per poterlo
        centrare sul player ovunque si trovi."""
        key = "light_overlay"
        if key not in self._cache:
            w, h = s.SCREEN_W * 2, s.SCREEN_H * 2
            surf = gfx.Surface((w, h), pygame.SRCALPHA)
            surf.fill((8, 6, 14, s.DARKNESS_ALPHA))
            r_max = s.LIGHT_RADIUS
            for r in range(r_max, 0, -6):
                a = int(s.DARKNESS_ALPHA * (r / r_max) ** 1.6)
                pygame.draw.circle(surf, (8, 6, 14, a), (w // 2, h // 2), r)
            self._cache[key] = surf
        return self._cache[key]

    # ── Font ──────────────────────────────────────────────────────────────────

    def font(self, size: int = 22, bold: bool = False, symbols: bool = False) -> pygame.font.Font:
        """symbols=True: font con i simboli dei controller PlayStation (✕ ○ □ △),
        che Consolas non ha."""
        key = f"font_{size}_{bold}_{symbols}"
        if key not in self._cache:
            family = "segoeuisymbol,dejavusans" if symbols else "consolas"
            self._cache[key] = gfx.font(lambda sz: pygame.font.SysFont(family, sz, bold=bold), size)
        return self._cache[key]

    def ui_font(self, size: int = 22, bold: bool = False) -> pygame.font.Font:
        """Font per i testi che mostrano comandi: con il controller usa il font coi simboli."""
        from game.input import InputManager
        return self.font(size, bold, symbols=InputManager.get().using_controller)
