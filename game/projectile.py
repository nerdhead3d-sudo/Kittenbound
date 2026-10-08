import math
import pygame
from game import settings as s
from game.asset_manager import AssetManager
from game import gfx


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
        style: str = None,          # "stone" (fionda) / "fire" / "knife" (boss) / None (sprite)
    ):
        super().__init__()
        self.style  = style
        self.reflected = False      # True: respinto da una parata
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
        if self.style == "knife":
            self._draw_knife(surface, camera_offset)
        elif self.style == "blade":
            from game.spells import draw_blade        # import qui: spells usa Projectile
            draw_blade(surface, self, camera_offset)
        elif self.style in ("stone", "fire"):
            self._draw_styled(surface, camera_offset)
        elif self.is_spell:
            cx = round(self.pos.x) - camera_offset[0]
            cy = round(self.pos.y) - camera_offset[1]
            t  = pygame.time.get_ticks() / 1000.0
            r  = 6 + int(2 * math.sin(t * 14.0))
            pygame.draw.circle(surface, (200, 240, 80),  (cx, cy), r)
            pygame.draw.circle(surface, (240, 200, 50),  (cx, cy), r - 2)
        else:
            surface.blit(self.image, (self.rect.x - camera_offset[0],
                                      self.rect.y - camera_offset[1]))

    def _draw_knife(self, surface: pygame.Surface, camera_offset: tuple):
        """Coltello del boss (sprite 3D in 32 direzioni) sollevato da terra, con ombra e scia."""
        cx = round(self.pos.x) - camera_offset[0]
        cy = round(self.pos.y) - camera_offset[1]
        frames = AssetManager.get().fx_frames("knife")
        shadow = gfx.Surface((26, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 90), shadow.get_rect())
        surface.blit(shadow, (cx - 13, cy - 5))
        lift = 14
        back = -self.vel.normalize() if self.vel.length_squared() > 0 else pygame.math.Vector2()
        for k in (3, 2, 1):                                   # scia argentata
            c = 25 * (3 - k)
            pygame.draw.line(surface, (150 + c, 160 + c, 175 + c),
                             (cx + back.x * 6 * k, cy - lift + back.y * 6 * k),
                             (cx + back.x * 6 * (k + 1), cy - lift + back.y * 6 * (k + 1)), 4 - k)
        if self.reflected:                                    # respinto: alone azzurro
            pygame.draw.circle(surface, (90, 190, 255), (cx, cy - lift), 16, 2)
        if not frames:
            pygame.draw.line(surface, (220, 225, 235), (cx, cy - lift),
                             (cx - back.x * 14, cy - lift - back.y * 14), 3)
            return
        angle = math.degrees(math.atan2(self.vel.y, self.vel.x)) % 360
        img   = frames[round(angle / (360 / len(frames))) % len(frames)]
        surface.blit(img, img.get_rect(center=(cx, cy - lift)))

    def _draw_styled(self, surface: pygame.Surface, camera_offset: tuple):
        cx = round(self.pos.x) - camera_offset[0]
        cy = round(self.pos.y) - camera_offset[1]
        if self.reflected:                                   # respinto: alone azzurro
            pygame.draw.circle(surface, (90, 190, 255), (cx, cy), 12, 2)
        back = -self.vel.normalize() if self.vel.length_squared() > 0 else pygame.math.Vector2()
        if self.style == "stone":
            for k, (r, c) in enumerate(((3, (110, 104, 96)), (2, (90, 86, 80)))):   # scia
                tx, ty = cx + back.x * 7 * (k + 1), cy + back.y * 7 * (k + 1)
                pygame.draw.circle(surface, c, (round(tx), round(ty)), r)
            pygame.draw.circle(surface, (40, 36, 34), (cx, cy), 6)
            pygame.draw.circle(surface, (150, 142, 132), (cx, cy), 5)
            pygame.draw.circle(surface, (205, 198, 186), (cx - 2, cy - 2), 2)
        else:                                                                     # sfera di fuoco
            for k in range(4):
                tx, ty = cx + back.x * 6 * (k + 1), cy + back.y * 6 * (k + 1)
                pygame.draw.circle(surface, (200 - k * 30, 70, 20), (round(tx), round(ty)), 6 - k)
            pygame.draw.circle(surface, (120, 30, 10), (cx, cy), 9)
            pygame.draw.circle(surface, (240, 110, 30), (cx, cy), 7)
            pygame.draw.circle(surface, (255, 220, 120), (cx - 1, cy - 1), 3)
