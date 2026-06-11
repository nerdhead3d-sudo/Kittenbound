import math
import pygame
from game import settings as s
from game.asset_manager import AssetManager


class Projectile(pygame.sprite.Sprite):
    """
    Proiettile generico (magie del player o attacchi nemici).
    owner: "player" | "enemy"
    """

    def __init__(
        self,
        x: float,
        y: float,
        direction,
        damage: int,
        owner: str = "player",
        speed: float = None,
        max_range: float = None,
        is_spell: bool = False,
    ):
        super().__init__()
        self.owner  = owner
        self.damage = damage
        self.speed  = speed if speed is not None else (
            s.SPELL_FIREBALL_SPEED if owner == "player" else s.ENEMY_PROJECTILE_SPEED
        )
        self._dist_left = max_range if max_range is not None else (
            600.0 if owner == "player" else float(s.ENEMY_PROJECTILE_RANGE)
        )

        self.is_spell = is_spell
        self.image    = AssetManager.get().projectile_sprite(owner)
        self.pos      = pygame.math.Vector2(x, y)
        self.rect     = self.image.get_rect(center=(int(x), int(y)))

        dir_vec = pygame.math.Vector2(direction)
        if dir_vec.length_squared() > 0:
            dir_vec.normalize_ip()
        self.vel = dir_vec * self.speed

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float, wall_rects=None):
        self.pos += self.vel * dt
        self.rect.center = (round(self.pos.x), round(self.pos.y))
        self._dist_left -= self.speed * dt

        if self._dist_left <= 0:
            self.kill()
            return

        if wall_rects:
            for wall in wall_rects:
                if self.rect.colliderect(wall):
                    self.kill()
                    return

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        if self.is_spell:
            cx = round(self.pos.x) - camera_offset[0]
            cy = round(self.pos.y) - camera_offset[1]
            t  = pygame.time.get_ticks() / 1000.0
            r  = 6 + int(2 * math.sin(t * 14.0))
            pygame.draw.circle(surface, (200, 240, 80),  (cx, cy), r)
            pygame.draw.circle(surface, (240, 200, 50),  (cx, cy), r - 2)
        else:
            surface.blit(self.image, (self.rect.x - camera_offset[0],
                                      self.rect.y - camera_offset[1]))
