import math
import pygame
from game.asset_manager import AssetManager


class Loot(pygame.sprite.Sprite):
    """Oggetto raccoglibile a terra (coin, hp, mp, orb = pallino rosso che cura poco).
    La logica di pickup è gestita da Room.update()."""

    def __init__(self, x: float, y: float, loot_type: str, value: int):
        super().__init__()
        self.loot_type = loot_type
        self.value     = value
        self.image     = AssetManager.get().loot_sprite(loot_type)
        self.rect      = self.image.get_rect(center=(int(x), int(y)))
        self.pos       = pygame.math.Vector2(x, y)
        self._phase    = (x * 0.37 + y * 0.11) % math.tau

    def draw(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        if self.loot_type == "orb":             # pallino rosso pulsante che fluttua
            t  = pygame.time.get_ticks() / 1000.0
            cx = round(self.pos.x) - camera_offset[0]
            cy = round(self.pos.y) - camera_offset[1] - 6 + round(2 * math.sin(t * 4 + self._phase))
            r  = 4 + round(math.sin(t * 6 + self._phase))
            pygame.draw.circle(surface, (110, 10, 20), (cx, cy), r + 3)
            pygame.draw.circle(surface, (230, 40, 50), (cx, cy), r + 1)
            pygame.draw.circle(surface, (255, 170, 160), (cx - 1, cy - 1), 2)
            return
        pos = (self.rect.x - camera_offset[0], self.rect.y - camera_offset[1])
        surface.blit(self.image, pos)
