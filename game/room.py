import math
import pygame
import random
from game import settings as s
from game.asset_manager import AssetManager
from game.loot import Loot

TILE_FLOOR = 0
TILE_WALL  = 1


class Room:
    """
    Singola stanza del dungeon.
    Gestisce: tile grid, wall rects, spawn nemici, proiettili nemici,
    collisioni, camera offset e stato (visited/cleared).
    """

    def __init__(
        self,
        cols: int = None,
        rows: int = None,
        doors: dict = None,
        enemy_specs: list = None,
        is_end: bool = False,
        room_type: str = None,
    ):
        rt = room_type or s.ROOM_TYPE_NORMAL
        self.room_type = rt
        self.cols = cols or (s.BOSS_ROOM_COLS if rt == s.ROOM_TYPE_BOSS else s.ROOM_COLS)
        self.rows = rows or (s.BOSS_ROOM_ROWS if rt == s.ROOM_TYPE_BOSS else s.ROOM_ROWS)

        # doors: {'N': bool, 'S': bool, 'E': bool, 'W': bool}
        self.doors = doors or {}

        self.tiles      = self._generate_tiles()
        self._base_wall_rects = self._build_wall_rects()
        self._door_tile_set: set = set()
        self._collect_door_tiles()
        self._door_rects = [
            pygame.Rect(c * s.TILE_SIZE, r * s.TILE_SIZE, s.TILE_SIZE, s.TILE_SIZE)
            for r, c in self._door_tile_set
        ]
        # I nemici non escono mai dalle porte; il player solo se la stanza non è bloccata
        self._enemy_wall_rects = self._base_wall_rects + self._door_rects
        self.wall_rects        = self._base_wall_rects

        self.is_end  = is_end
        self._locked = False

        self.enemies           = pygame.sprite.Group()
        self.enemy_projectiles = pygame.sprite.Group()
        self.loot              = pygame.sprite.Group()

        self.visited = False

        if enemy_specs:
            self._spawn_enemies(enemy_specs)

        # Auto-clear se nessun nemico è stato spawnato
        self.cleared = len(self.enemies) == 0

        # Chest: presente nelle stanze speciali e boss, bloccata finché la stanza non è liberata
        self.has_chest    = rt in (s.ROOM_TYPE_SPECIAL, s.ROOM_TYPE_BOSS)
        self.chest_tier   = (3 if rt == s.ROOM_TYPE_BOSS else
                             2 if rt == s.ROOM_TYPE_SPECIAL else 1)
        self.chest_opened = False

    # ── Generazione tiles ─────────────────────────────────────────────────────

    def _generate_tiles(self) -> list:
        tiles = []
        for r in range(self.rows):
            row = []
            for c in range(self.cols):
                is_border = (r == 0 or r == self.rows - 1 or
                             c == 0 or c == self.cols - 1)
                row.append(TILE_WALL if is_border else TILE_FLOOR)
            tiles.append(row)

        if self.room_type != s.ROOM_TYPE_BOSS:
            self._add_obstacles(tiles)
        self._carve_doors(tiles)
        return tiles

    def _add_obstacles(self, tiles: list):
        """Pilastri interni casuali, lontani dal centro (spawn player)."""
        cr, cc = self.rows // 2, self.cols // 2
        candidates = [
            (r, c)
            for r in range(2, self.rows - 2)
            for c in range(2, self.cols - 2)
            if abs(r - cr) >= 3 or abs(c - cc) >= 3
        ]
        random.shuffle(candidates)
        for r, c in candidates[:random.randint(4, 8)]:
            tiles[r][c] = TILE_WALL

    def _carve_doors(self, tiles: list):
        mid_c = self.cols // 2
        mid_r = self.rows // 2
        openings = {
            'N': [(0, mid_c - 1), (0, mid_c)],
            'S': [(self.rows - 1, mid_c - 1), (self.rows - 1, mid_c)],
            'E': [(mid_r - 1, self.cols - 1), (mid_r, self.cols - 1)],
            'W': [(mid_r - 1, 0), (mid_r, 0)],
        }
        for direction, is_open in self.doors.items():
            if is_open:
                for r, c in openings[direction]:
                    tiles[r][c] = TILE_FLOOR

    def _collect_door_tiles(self):
        mid_c = self.cols // 2
        mid_r = self.rows // 2
        all_openings = {
            'N': [(0, mid_c - 1), (0, mid_c)],
            'S': [(self.rows - 1, mid_c - 1), (self.rows - 1, mid_c)],
            'E': [(mid_r - 1, self.cols - 1), (mid_r, self.cols - 1)],
            'W': [(mid_r - 1, 0), (mid_r, 0)],
        }
        for direction, is_open in self.doors.items():
            if is_open:
                for pos in all_openings[direction]:
                    self._door_tile_set.add(pos)

    def _build_wall_rects(self) -> list:
        rects = []
        for r in range(self.rows):
            for c in range(self.cols):
                if self.tiles[r][c] == TILE_WALL:
                    rects.append(pygame.Rect(
                        c * s.TILE_SIZE, r * s.TILE_SIZE,
                        s.TILE_SIZE, s.TILE_SIZE,
                    ))
        return rects

    # ── Spawn nemici ──────────────────────────────────────────────────────────

    def _spawn_enemies(self, enemy_specs: list):
        """enemy_specs: [(EnemyClass, count), ...]"""
        cx_px = (self.cols // 2) * s.TILE_SIZE
        cy_px = (self.rows // 2) * s.TILE_SIZE

        floor_positions = [
            (c * s.TILE_SIZE + s.TILE_SIZE // 2,
             r * s.TILE_SIZE + s.TILE_SIZE // 2)
            for r in range(2, self.rows - 2)
            for c in range(2, self.cols - 2)
            if self.tiles[r][c] == TILE_FLOOR
        ]
        # Esclude area vicina al centro (zona spawn player)
        spawn_pool = [
            pos for pos in floor_positions
            if abs(pos[0] - cx_px) > s.TILE_SIZE * 3 or
               abs(pos[1] - cy_px) > s.TILE_SIZE * 3
        ]
        random.shuffle(spawn_pool)

        idx = 0
        for EnemyClass, count in enemy_specs:
            for _ in range(count):
                if idx >= len(spawn_pool):
                    break
                x, y = spawn_pool[idx]
                self.enemies.add(EnemyClass(x, y))
                idx += 1

    # ── Proprietà ─────────────────────────────────────────────────────────────

    @property
    def pixel_w(self) -> int:
        return self.cols * s.TILE_SIZE

    @property
    def pixel_h(self) -> int:
        return self.rows * s.TILE_SIZE

    # ── Camera ────────────────────────────────────────────────────────────────

    def get_camera_offset(self, player_pos: pygame.math.Vector2) -> tuple:
        """
        Restituisce (cam_x, cam_y): da sottrarre alle coord world per ottenere screen.
        Se la stanza è più piccola dello schermo, viene centrata (cam negativo).
        """
        if self.pixel_w <= s.SCREEN_W:
            cam_x = -((s.SCREEN_W - self.pixel_w) // 2)
        else:
            cam_x = int(max(0, min(
                self.pixel_w - s.SCREEN_W,
                player_pos.x - s.SCREEN_W // 2,
            )))

        if self.pixel_h <= s.SCREEN_H:
            cam_y = -((s.SCREEN_H - self.pixel_h) // 2)
        else:
            cam_y = int(max(0, min(
                self.pixel_h - s.SCREEN_H,
                player_pos.y - s.SCREEN_H // 2,
            )))

        return cam_x, cam_y

    # ── Ingresso stanza ───────────────────────────────────────────────────────

    def enter(self, player, from_direction: str = None):
        """Posiziona il player all'ingresso corretto e segna la stanza come visitata."""
        self.visited = True
        # Attiva il lockdown nelle stanze speciali non ancora liberate
        if self.room_type in (s.ROOM_TYPE_SPECIAL, s.ROOM_TYPE_BOSS) and not self.cleared:
            self._set_locked(True)
        mid_c = self.cols // 2
        mid_r = self.rows // 2

        entry_positions = {
            'N': (mid_c * s.TILE_SIZE, 2 * s.TILE_SIZE),
            'S': (mid_c * s.TILE_SIZE, (self.rows - 3) * s.TILE_SIZE),
            'E': ((self.cols - 3) * s.TILE_SIZE, mid_r * s.TILE_SIZE),
            'W': (2 * s.TILE_SIZE, mid_r * s.TILE_SIZE),
        }
        px, py = entry_positions.get(from_direction, (self.pixel_w // 2, self.pixel_h // 2))
        player.pos.x = float(px)
        player.pos.y = float(py)
        player.rect.center = (round(px), round(py))

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float, player, player_projectiles):
        # Resetta le riduzioni danno — saranno riapplicate dallo Stregone durante il suo update
        for enemy in self.enemies:
            enemy.damage_reduction = 0.0

        # AI nemici + gestione spawn in attesa (Esploratore)
        for enemy in list(self.enemies):
            enemy.update(dt, player, self._enemy_wall_rects,
                         self.enemy_projectiles, self.tiles, self.enemies)
            if hasattr(enemy, 'pending_spawns') and enemy.pending_spawns:
                for cls, ex, ey in enemy.pending_spawns:
                    sx, sy = self._find_spawn_near(ex, ey)
                    self.enemies.add(cls(float(sx), float(sy)))
                enemy.pending_spawns.clear()

        # Movimento proiettili nemici + collisione con muri
        self.enemy_projectiles.update(dt, self.wall_rects)

        # Collisione: proiettili player → nemici
        hits = pygame.sprite.groupcollide(self.enemies, player_projectiles, False, True)
        for enemy, projs in hits.items():
            was_alive = enemy.alive
            for proj in projs:
                if enemy.alive:
                    enemy.take_damage(proj.damage)
                    if getattr(proj, 'is_spell', False):
                        player.mark_enemy(enemy)
            if was_alive and not enemy.alive:
                player.gain_xp(enemy.XP)
                gold = random.randint(s.GOLD_DROP_MIN, s.GOLD_DROP_MAX) * s.COIN_VALUE
                self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "coin", gold))
                roll = random.random()
                if roll < 0.15:
                    self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "hp", s.POTION_HP_VALUE))
                elif roll < 0.25:
                    self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "mp", s.POTION_ENERGY_VALUE))

        # Collisione: proiettili nemici → player
        for proj in list(self.enemy_projectiles):
            if proj.rect.colliderect(player.rect):
                player.take_damage(proj.damage)
                proj.kill()

        # Check stanza liberata + sblocco porte
        if not self.cleared and len(self.enemies) == 0:
            self.cleared = True
        if self._locked and self.cleared:
            self._set_locked(False)

        # Raccolta loot
        for item in list(self.loot):
            if item.rect.colliderect(player.rect):
                if item.loot_type == "coin":
                    player.gold += item.value
                elif item.loot_type == "hp":
                    player.heal(item.value)
                elif item.loot_type == "mp":
                    player.restore_energy(item.value)
                item.kill()

        # Apertura chest (solo dopo aver liberato la stanza)
        if self.has_chest and self.cleared and not self.chest_opened:
            cx, cy = self.pixel_w // 2, self.pixel_h // 2
            if player.pos.distance_to((cx, cy)) <= s.CHEST_OPEN_RADIUS:
                self.chest_opened = True
                self._open_chest(player)

    # ── Helper methods ────────────────────────────────────────────────────────

    def _set_locked(self, locked: bool):
        """Lockdown: le porte diventano muri solidi finché la stanza non è liberata."""
        self._locked    = locked
        self.wall_rects = self._enemy_wall_rects if locked else self._base_wall_rects

    def _open_chest(self, player):
        if self.chest_tier == 3:                    # boss
            player.gold += s.CHEST_BOSS_GOLD
            player.hp     = float(player.hp_max)
            player.energy = float(player.energy_max)
        elif self.chest_tier == 2:                  # stanza speciale
            player.gold += s.CHEST_SPECIAL_GOLD
            player.heal(s.POTION_HP_VALUE)
            player.restore_energy(s.POTION_ENERGY_VALUE)

    def apply_single_damage(self, enemy, amount: int, player):
        """Danno diretto a un singolo nemico (artiglio del balzo)."""
        if enemy not in self.enemies:
            return
        was_alive = enemy.alive
        enemy.take_damage(amount)
        if was_alive and not enemy.alive:
            player.gain_xp(enemy.XP)
            gold = random.randint(s.GOLD_DROP_MIN, s.GOLD_DROP_MAX) * s.COIN_VALUE
            self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "coin", gold))
            roll = random.random()
            if roll < 0.15:
                self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "hp", s.POTION_HP_VALUE))
            elif roll < 0.25:
                self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "mp", s.POTION_ENERGY_VALUE))

    def apply_melee(self, hitbox: pygame.Rect, damage: int, player):
        """Applica danno melee a tutti i nemici nel hitbox."""
        for enemy in list(self.enemies):
            if not hitbox.colliderect(enemy.rect):
                continue
            was_alive = enemy.alive
            enemy.take_damage(damage)
            if was_alive and not enemy.alive:
                player.gain_xp(enemy.XP)
                gold = random.randint(s.GOLD_DROP_MIN, s.GOLD_DROP_MAX) * s.COIN_VALUE
                self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "coin", gold))
                roll = random.random()
                if roll < 0.15:
                    self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "hp", s.POTION_HP_VALUE))
                elif roll < 0.25:
                    self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "mp", s.POTION_ENERGY_VALUE))

    def _find_spawn_near(self, hint_x: float, hint_y: float) -> tuple:
        """Trova il tile percorribile più vicino a (hint_x, hint_y)."""
        best, best_d2 = (hint_x, hint_y), float('inf')
        for r in range(1, self.rows - 1):
            for c in range(1, self.cols - 1):
                if self.tiles[r][c] == TILE_FLOOR:
                    px = c * s.TILE_SIZE + s.TILE_SIZE // 2
                    py = r * s.TILE_SIZE + s.TILE_SIZE // 2
                    d2 = (px - hint_x) ** 2 + (py - hint_y) ** 2
                    if d2 < best_d2:
                        best_d2 = d2
                        best    = (px, py)
        return best

    def _draw_locked_doors(self, surface: pygame.Surface, camera_offset: tuple):
        """Disegna sbarre rosse sulle porte quando la stanza è bloccata."""
        cam_x, cam_y = camera_offset
        T     = s.TILE_SIZE
        mid_c = self.cols // 2
        mid_r = self.rows // 2

        door_world_rects = {
            'N': pygame.Rect((mid_c - 1) * T, 0,              T * 2, T),
            'S': pygame.Rect((mid_c - 1) * T, (self.rows-1)*T, T * 2, T),
            'E': pygame.Rect((self.cols-1)*T, (mid_r - 1) * T, T,     T * 2),
            'W': pygame.Rect(0,               (mid_r - 1) * T, T,     T * 2),
        }
        for direction, has_door in self.doors.items():
            if not has_door:
                continue
            dr = door_world_rects[direction]
            sx, sy, sw, sh = dr.x - cam_x, dr.y - cam_y, dr.width, dr.height

            overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
            overlay.fill((110, 22, 22, 210))
            surface.blit(overlay, (sx, sy))

            bar_c = (72, 12, 12)
            if sh > sw:                         # porta verticale (E / W)
                for by in range(0, sh, T // 2):
                    pygame.draw.rect(surface, bar_c, (sx, sy + by, sw, 4))
            else:                               # porta orizzontale (N / S)
                for bx in range(0, sw, T // 2):
                    pygame.draw.rect(surface, bar_c, (sx + bx, sy, 4, sh))

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        cam_x, cam_y = camera_offset

        # Portale della stanza finale (solo dopo aver sconfitto il boss)
        if self.is_end and self.cleared:
            t   = pygame.time.get_ticks() / 1000.0
            pcx = self.pixel_w // 2 - cam_x
            pcy = self.pixel_h // 2 - cam_y
            pr  = int(22 + 6 * math.sin(t * 2.5))
            pygame.draw.circle(surface, (20, 75, 45),    (pcx, pcy), pr + 14)
            pygame.draw.circle(surface, (55, 170, 90),   (pcx, pcy), pr, 3)
            pygame.draw.circle(surface, (150, 235, 170), (pcx, pcy), pr // 2)
            pygame.draw.circle(surface, (220, 255, 230), (pcx, pcy), 5)

        for r in range(self.rows):
            for c in range(self.cols):
                sx = c * s.TILE_SIZE - cam_x
                sy = r * s.TILE_SIZE - cam_y

                if self.tiles[r][c] == TILE_WALL:
                    pygame.draw.rect(surface, s.C_WALL,
                                     (sx, sy, s.TILE_SIZE, s.TILE_SIZE))
                    # Highlight bordo superiore/sinistro per effetto pietra 3D
                    pygame.draw.line(surface, s.C_WALL_LIT,
                                     (sx, sy), (sx + s.TILE_SIZE - 1, sy))
                    pygame.draw.line(surface, s.C_WALL_LIT,
                                     (sx, sy), (sx, sy + s.TILE_SIZE - 1))
                    pygame.draw.rect(surface, (35, 32, 40),
                                     (sx, sy, s.TILE_SIZE, s.TILE_SIZE), 1)
                else:
                    color = s.C_FLOOR if (r + c) % 2 == 0 else s.C_FLOOR_ALT
                    pygame.draw.rect(surface, color,
                                     (sx, sy, s.TILE_SIZE, s.TILE_SIZE))
                    # Evidenzia porte aperte con bordo verde
                    if (r, c) in self._door_tile_set:
                        pygame.draw.rect(surface, s.C_DOOR_OPEN,
                                         (sx + 2, sy + 2,
                                          s.TILE_SIZE - 4, s.TILE_SIZE - 4), 2)

        # Loot a terra
        for item in self.loot:
            item.draw(surface, camera_offset)

        # Chest: visibile sempre (scura/bloccata finché la stanza non è liberata)
        if self.has_chest and not self.chest_opened:
            chest_surf = AssetManager.get().chest_sprite()
            csx = self.pixel_w // 2 - cam_x - chest_surf.get_width() // 2
            csy = self.pixel_h // 2 - cam_y - chest_surf.get_height() // 2
            surface.blit(chest_surf, (csx, csy))
            if not self.cleared:
                lock_ov = pygame.Surface(chest_surf.get_size(), pygame.SRCALPHA)
                lock_ov.fill((0, 0, 0, 165))
                surface.blit(lock_ov, (csx, csy))

        # Nemici e loro proiettili
        for enemy in self.enemies:
            enemy.draw(surface, camera_offset)
        for proj in self.enemy_projectiles:
            proj.draw(surface, camera_offset)

        # Porte bloccate (stanza speciale in lockdown)
        if self._locked:
            self._draw_locked_doors(surface, camera_offset)

