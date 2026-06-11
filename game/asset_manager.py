import pygame
from pathlib import Path
from game import settings as s

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
        self._cache: dict[str, pygame.Surface] = {}

    # ── PNG loader ────────────────────────────────────────────────────────────

    def _load_png(self, key: str) -> "pygame.Surface | None":
        """Carica assets/sprites/<key>.png; restituisce None se assente o corrotto."""
        path = _SPRITES_DIR / f"{key}.png"
        if not path.exists():
            return None
        try:
            return pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            return None

    # ── Player ────────────────────────────────────────────────────────────────

    def player_sprite(self) -> pygame.Surface:
        key = "player"
        if key not in self._cache:
            self._cache[key] = self._load_png(key) or self._make_player()
        return self._cache[key]

    def _make_player(self) -> pygame.Surface:
        size = s.PLAYER_RADIUS * 2 + 8
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
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
            "skeleton":      s.C_SKELETON,
        }
        color = color_map.get(enemy_type, (150, 150, 150))
        size = 36
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
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
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
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
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
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
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
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

    # ── Font ──────────────────────────────────────────────────────────────────

    def font(self, size: int = 22, bold: bool = False) -> pygame.font.Font:
        key = f"font_{size}_{bold}"
        if key not in self._cache:
            self._cache[key] = pygame.font.SysFont("consolas", size, bold=bold)
        return self._cache[key]
