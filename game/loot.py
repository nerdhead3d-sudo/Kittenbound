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
        if self.loot_type == "bag":
            self._draw_bag(surface, camera_offset)
            return
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
        if self.loot_type in ("hp", "mp"):        # le pozioni ondeggiano piano sopra l'ombra
            t = pygame.time.get_ticks() / 1000.0
            pos = (pos[0], pos[1] - 6 + round(2 * math.sin(t * 3 + self._phase)))
        surface.blit(self.image, pos)

    def _draw_bag(self, surface, camera_offset):
        """Sacca di cuoio con le monete: quello che hai perso morendo. Brilla per farsi trovare."""
        t  = pygame.time.get_ticks() / 1000.0
        cx = round(self.pos.x) - camera_offset[0]
        cy = round(self.pos.y) - camera_offset[1] + round(1.5 * math.sin(t * 3))
        glow = 0.6 + 0.4 * math.sin(t * 4)
        pygame.draw.circle(surface, (round(90 * glow), round(70 * glow), 10), (cx, cy - 4), 22, 2)
        pygame.draw.ellipse(surface, (70, 44, 24), (cx - 13, cy - 14, 26, 22))          # sacco
        pygame.draw.ellipse(surface, (122, 80, 44), (cx - 12, cy - 15, 24, 20))
        pygame.draw.ellipse(surface, (150, 104, 62), (cx - 8, cy - 13, 10, 8))           # luce
        pygame.draw.polygon(surface, (100, 64, 34), [(cx - 6, cy - 15), (cx + 6, cy - 15), (cx + 3, cy - 21), (cx - 3, cy - 21)])
        pygame.draw.line(surface, (210, 170, 70), (cx - 6, cy - 16), (cx + 6, cy - 16), 2)  # laccio
        for k in range(3):                                                               # monete che brillano
            a = t * 2 + k * 2.1
            pygame.draw.circle(surface, (250, 210, 70), (cx + round(math.cos(a) * 9), cy - 18 + round(math.sin(a) * 3)), 2)
