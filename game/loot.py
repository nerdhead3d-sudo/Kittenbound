import pygame
from game.asset_manager import AssetManager


class Loot(pygame.sprite.Sprite):
    """Oggetto raccoglibile a terra (coin, hp, mp).
    La logica di pickup è gestita da Room.update()."""

    def __init__(self, x: float, y: float, loot_type: str, value: int):
        super().__init__()
        self.loot_type = loot_type
        self.value     = value
        self.image     = AssetManager.get().loot_sprite(loot_type)
        self.rect      = self.image.get_rect(center=(int(x), int(y)))

    def draw(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        pos = (self.rect.x - camera_offset[0], self.rect.y - camera_offset[1])
        surface.blit(self.image, pos)
