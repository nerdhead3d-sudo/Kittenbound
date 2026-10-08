import math
import pygame
import random
from game import settings as s
from game.asset_manager import AssetManager
from game.loot import Loot
from game.sound import play
from game import gfx

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
        floor: int = 1,
    ):
        rt = room_type or s.ROOM_TYPE_NORMAL
        self.floor = floor
        self._reward_mult = 1 + s.FLOOR_REWARD_SCALE * (floor - 1)
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
        self._torch_tiles = self._place_torches()
        self._wall_art    = self._build_wall_art()
        self._floor_surf = None     # pavimento pre-renderizzato (al primo draw)

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

    def _build_wall_art(self) -> dict:
        """Divide i muri in blocchi di pietra da 1-3 tile come nella stanza dipinta.
        Per ogni tile di muro: (cima, area della cima, mattoni, area dei mattoni); ogni tile
        disegna solo la sua parte del blocco, così l'ordinamento per Y resta per tile."""
        slabs = AssetManager.get().wall_slabs()
        if not slabs or not slabs.get("h2") or not slabs.get("p"):
            return {}
        T, H = s.TILE_SIZE, s.WALL_HEIGHT
        rng  = random.Random(self.cols * 1000 + self.rows * 37 + sum(sum(row) for row in self.tiles))
        art, done = {}, set()

        def bricks_for(r, c, face, area):
            if self._is_wall(r + 1, c):                  # sotto c'è altro muro: mattoni nascosti
                return None, None
            if face is None:
                face, area = rng.choice(slabs["p"])[1], None
            return face, area

        def split(length):
            parts = []
            while length > 0:
                n = min(length, rng.choice((1, 2, 2, 3, 3)))
                if length - n == 1 and n > 1 and not slabs.get("h1"):
                    n -= 1
                parts.append(n)
                length -= n
            return parts

        # 1) muri orizzontali: file di almeno 2 tile nella stessa riga
        for r in range(self.rows):
            c = 0
            while c < self.cols:
                if not self._is_wall(r, c):
                    c += 1
                    continue
                start = c
                while c < self.cols and self._is_wall(r, c):
                    c += 1
                if c - start < 2:
                    continue
                x = start
                for n in split(c - start):
                    kind = f"h{n}" if slabs.get(f"h{n}") else "h2"
                    n_art = int(kind[1])
                    top, face = rng.choice(slabs[kind])
                    for i in range(n):
                        k = min(i, n_art - 1)
                        f, fa = bricks_for(r, x + i, face, pygame.Rect(k * T, 0, T, H) if face else None)
                        art[(r, x + i)] = (top, pygame.Rect(k * T, 0, T, T), f, fa)
                        done.add((r, x + i))
                    x += n

        # 2) muri verticali: colonne di tile rimaste
        for c in range(self.cols):
            r = 0
            while r < self.rows:
                if not self._is_wall(r, c) or (r, c) in done:
                    r += 1
                    continue
                start = r
                while r < self.rows and self._is_wall(r, c) and (r, c) not in done:
                    r += 1
                y = start
                while y < r:
                    n = min(r - y, rng.choice((1, 2, 2)))
                    if n == 1 and r - start >= 2 and slabs.get("v1"):
                        kind = "v1"
                    elif n == 2 and slabs.get("v2"):
                        kind = "v2"
                    else:
                        kind, n = "p", 1
                    top, face = rng.choice(slabs[kind])
                    for j in range(n):
                        f, fa = bricks_for(y + j, c, face if kind == "p" else None, None)
                        art[(y + j, c)] = (top, pygame.Rect(0, j * T, T, T) if kind != "p" else None, f, fa)
                        done.add((y + j, c))
                    y += n
        return art

    def _place_torches(self) -> set:
        """Torce sul muro a nord (quello che si vede di fronte), lontane dalle porte."""
        if AssetManager.get().torch() is None:
            return set()
        doors = {c for r, c in self._door_tile_set if r == 0}
        spots = set()
        for c in range(2, self.cols - 2):
            if (c - 2) % 5 == 0 and self._is_wall(0, c) and not self._is_wall(1, c)                     and all(abs(c - d) > 1 for d in doors):
                spots.add((0, c))
        return spots

    def light_sources(self) -> list:
        """Luci della stanza (x, y, raggio) in coordinate mondo: torce, nemici che caricano, proiettili."""
        T = s.TILE_SIZE
        lights = [(c * T + T // 2, r * T + T - s.WALL_HEIGHT // 2, s.TORCH_LIGHT_RADIUS)
                  for r, c in self._torch_tiles]
        # Gli avvisi d'attacco devono vedersi anche al buio: chi carica un colpo si illumina
        for e in self.enemies:
            frac = e._windup_frac() if hasattr(e, "_windup_frac") else (
                1.0 - e._windup / e._windup_total if e._windup > 0 else None)
            if frac is not None:
                lights.append((round(e.pos.x), round(e.pos.y) - 10, 70 + round(30 * frac / 4) * 4))
            for pos, t, warn, landed in getattr(e, "_rocks", ()):   # dove stanno per cadere i massi
                if not landed and t >= 0:
                    lights.append((round(pos.x), round(pos.y), 64))
        for proj in self.enemy_projectiles:                # proiettili in arrivo
            lights.append((round(proj.pos.x), round(proj.pos.y), 48))
        return lights

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
                self.enemies.add(EnemyClass(x, y).scale_for_floor(self.floor))
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

        if self.pixel_h + s.WALL_HEIGHT <= s.SCREEN_H:
            # Centra includendo la cima dei muri a nord, che sporge di WALL_HEIGHT
            cam_y = -((s.SCREEN_H - self.pixel_h - s.WALL_HEIGHT) // 2) - s.WALL_HEIGHT
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
            play("door_lock", 0.9)
            if self.room_type == s.ROOM_TYPE_BOSS:
                play("boss_roar", 0.8)
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

        # Corpi solidi: ogni nemico si ferma contro gli altri nemici e contro il player
        bodies = [e.rect for e in self.enemies]
        if getattr(player, "decoy", None) is None:    # con l'Ombra il gatto è come un fantasma
            bodies.append(player.rect)

        # AI nemici + gestione spawn in attesa (Esploratore)
        # Ombra Felina: i nemici inseguono e colpiscono l'ombra invece del gatto
        target = player.decoy if getattr(player, "decoy", None) is not None else player
        for enemy in list(self.enemies):
            enemy._bodies = bodies
            enemy.update(dt, target, self._enemy_wall_rects,
                         self.enemy_projectiles, self.tiles, self.enemies)
            if hasattr(enemy, 'pending_spawns') and enemy.pending_spawns:
                for cls, ex, ey in enemy.pending_spawns:
                    sx, sy = self._find_spawn_near(ex, ey)
                    reinforcement = cls(float(sx), float(sy)).scale_for_floor(self.floor)
                    reinforcement._aggro = True          # arrivano già sapendo dove sei
                    self.enemies.add(reinforcement)
                enemy.pending_spawns.clear()

        self._separate_enemies()

        # Movimento proiettili nemici + collisione con muri
        self.enemy_projectiles.update(dt, self.wall_rects)

        # Collisione: proiettili player → nemici
        hits = pygame.sprite.groupcollide(self.enemies, player_projectiles, False, False)
        for enemy, projs in hits.items():
            was_alive = enemy.alive
            for proj in projs:
                if getattr(proj, "piercing", False):  # lame spettrali: trapassano, una volta a nemico
                    hit_set = proj.__dict__.setdefault("hit_set", set())
                    if id(enemy) in hit_set:
                        continue
                    hit_set.add(id(enemy))
                else:
                    proj.kill()
                if enemy.alive:
                    enemy.take_damage(proj.damage, pierce=getattr(proj, 'reflected', False))
                    if getattr(proj, 'is_spell', False):
                        player.mark_enemy(enemy)
                        play("spell_mark", 0.8)
                    else:
                        play("hit", 0.7)
            if was_alive and not enemy.alive:
                self._on_enemy_killed(enemy, player)

        # Parata: i proiettili vicini (davanti al gatto) vengono respinti verso i nemici
        if player.parrying:
            for proj in list(self.enemy_projectiles):
                to_proj = proj.pos - player.pos
                d = to_proj.length()
                if d <= s.PARRY_RADIUS and (d < 1 or to_proj.normalize().dot(player.facing) > -0.35):
                    self._reflect(proj, player, player_projectiles)

        # Collisione: proiettili nemici → player
        for proj in list(self.enemy_projectiles):
            if proj.rect.colliderect(player.rect):
                player.take_damage(proj.damage)
                proj.kill()

        # Check stanza liberata + sblocco porte
        if not self.cleared and len(self.enemies) == 0:
            self.cleared = True
            play("room_clear", 0.7)
        if self._locked and self.cleared:
            self._set_locked(False)
            play("door_open", 0.8)

        # Contrattacchi automatici delle parate perfette (passano l'armatura del boss)
        for enemy in player.counter_targets:
            dmg = int((s.PLAYER_MELEE_DAMAGE + player.melee_damage_bonus) * s.PARRY_COUNTER_MULT)
            self.apply_single_damage(enemy, dmg, player, pierce=True)
        player.counter_targets.clear()

        # Raccolta loot (i pallini rossi vicini volano verso il gatto)
        for item in list(self.loot):
            if item.loot_type == "orb":
                to_p = player.pos - item.pos
                if 0 < to_p.length() <= s.ORB_MAGNET_RANGE:
                    item.pos += to_p.normalize() * min(to_p.length(), s.ORB_MAGNET_SPEED * dt)
                    item.rect.center = (round(item.pos.x), round(item.pos.y))
            if item.rect.colliderect(player.rect):
                if item.loot_type == "orb":
                    player.heal(item.value)
                    play("orb", 0.5)
                elif item.loot_type == "coin":
                    player.gold += item.value
                    play("coin", 0.6)
                elif item.loot_type == "hp":
                    player.heal(item.value)
                    play("potion", 0.8)
                elif item.loot_type == "mp":
                    player.restore_energy(item.value)
                    play("potion_mana", 0.8)
                item.kill()

        # Apertura chest (solo dopo aver liberato la stanza)
        if self.has_chest and self.cleared and not self.chest_opened:
            cx, cy = self.pixel_w // 2, self.pixel_h // 2
            if player.pos.distance_to((cx, cy)) <= s.CHEST_OPEN_RADIUS:
                self.chest_opened = True
                self._open_chest(player)
                play("chest", 0.9)

    # ── Helper methods ────────────────────────────────────────────────────────

    def _set_locked(self, locked: bool):
        """Lockdown: le porte diventano muri solidi finché la stanza non è liberata."""
        self._locked    = locked
        self.wall_rects = self._enemy_wall_rects if locked else self._base_wall_rects

    def _reflect(self, proj, player, player_projectiles):
        """Rimanda il proiettile verso il nemico più vicino, più veloce e più dannoso."""
        target = min(self.enemies, key=lambda e: (e.pos - proj.pos).length_squared(), default=None)
        aim = (target.pos - proj.pos) if target is not None else -proj.vel
        if aim.length_squared() == 0:
            aim = pygame.math.Vector2(player.facing)
        proj.speed     *= s.PARRY_SPEED_MULT
        proj.vel        = aim.normalize() * proj.speed
        perfect         = player.perfect_parry
        if proj.style == "knife":
            mult = s.PARRY_KNIFE_MULT[1 if perfect else 0]
        else:
            mult = s.PARRY_PERFECT_PROJ if perfect else s.PARRY_DMG_MULT
        proj.damage     = int(proj.damage * mult)
        proj.owner      = "player"
        proj.reflected  = True
        proj._dist_left = 800.0
        proj.kill()
        player_projectiles.add(proj)
        player.on_parry(pygame.math.Vector2(proj.pos), perfect)

    def _separate_enemies(self):
        """Allontana i nemici sovrapposti (es. rinforzi appena arrivati) senza farli
        entrare nei muri."""
        enemies = list(self.enemies)
        for i, a in enumerate(enemies):
            for b in enemies[i + 1:]:
                if not a.rect.colliderect(b.rect):
                    continue
                push = a.pos - b.pos
                if push.length_squared() < 1e-6:
                    push = pygame.math.Vector2(1, 0).rotate(random.uniform(0, 360))
                push.scale_to_length(1.5)
                a._move_axes(push, self._enemy_wall_rects)
                b._move_axes(-push, self._enemy_wall_rects)

    def _on_enemy_killed(self, enemy, player):
        """XP, oro e possibile pozione quando un nemico muore."""
        player.gain_xp(enemy.XP)
        play("boss_death" if enemy.ENEMY_TYPE == "boss" else "enemy_death", 0.8)
        gold = round(random.randint(s.GOLD_DROP_MIN, s.GOLD_DROP_MAX) * s.COIN_VALUE * self._reward_mult)
        self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "coin", gold))
        if random.random() < s.ORB_DROP_CHANCE:            # pallini rossi sparsi attorno
            for _ in range(random.randint(1, s.ORB_DROP_MAX)):
                off = pygame.math.Vector2(random.uniform(14, 30), 0).rotate(random.uniform(0, 360))
                self.loot.add(Loot(enemy.pos.x + off.x, enemy.pos.y + off.y, "orb", s.ORB_HEAL))
        roll = random.random()
        if roll < s.POTION_HP_CHANCE:
            self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "hp", s.POTION_HP_VALUE))
        elif roll < s.POTION_HP_CHANCE + s.POTION_EN_CHANCE:
            self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "mp", s.POTION_ENERGY_VALUE))

    def _open_chest(self, player):
        if self.chest_tier == 3:                    # boss
            player.gold += round(s.CHEST_BOSS_GOLD * self._reward_mult)
            player.hp     = float(player.hp_max)
            player.energy = float(player.energy_max)
        elif self.chest_tier == 2:                  # stanza speciale
            player.gold += round(s.CHEST_SPECIAL_GOLD * self._reward_mult)
            player.heal(s.POTION_HP_VALUE)
            player.restore_energy(s.POTION_ENERGY_VALUE)

    def apply_single_damage(self, enemy, amount: int, player, pierce: bool = False):
        """Danno diretto a un singolo nemico (artiglio del balzo, contrattacco)."""
        if enemy not in self.enemies:
            return
        was_alive = enemy.alive
        enemy.take_damage(amount, pierce=pierce)
        play("claw_heavy")
        if was_alive and not enemy.alive:
            self._on_enemy_killed(enemy, player)

    def apply_melee(self, hitbox: pygame.Rect, damage: int, player):
        """Applica danno melee a tutti i nemici nel hitbox."""
        hit_any = False
        for enemy in list(self.enemies):
            if not hitbox.colliderect(enemy.rect):
                continue
            hit_any   = True
            was_alive = enemy.alive
            enemy.take_damage(damage)
            if was_alive and not enemy.alive:
                self._on_enemy_killed(enemy, player)
        if hit_any:
            play("hit", 0.9)

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

    # ── Draw (finto 3D) ───────────────────────────────────────────────────────
    #
    # Ordine: pavimento pre-renderizzato (con ombra alla base dei muri) → ombre a
    # terra → muri, porte bloccate e personaggi ordinati per Y della base: chi sta
    # più in basso sullo schermo copre chi sta dietro. I muri hanno una faccia
    # frontale alta WALL_HEIGHT px e la cima sporge verso l'alto sulla riga precedente.

    def _is_wall(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols and self.tiles[r][c] == TILE_WALL

    def _floor_surface(self) -> pygame.Surface:
        if self._floor_surf is None:
            self._floor_surf = self._render_floor()
        return self._floor_surf

    def _render_floor(self) -> pygame.Surface:
        T    = s.TILE_SIZE
        surf = gfx.Surface((self.pixel_w, self.pixel_h), pygame.SRCALPHA)
        rng  = random.Random(id(self))
        grout_dark = (58, 51, 45)
        dark, light = AssetManager.get().floor_tiles()   # piastrelle dalla stanza dipinta
        for r in range(self.rows):
            for c in range(self.cols):
                if self.tiles[r][c] == TILE_WALL:
                    continue
                x, y  = c * T, r * T
                if dark and light:                       # scacchiera come nel dipinto
                    surf.blit(rng.choice(dark if (r + c) % 2 else light), (x, y))
                    continue
                shade = rng.randint(-7, 7)
                base  = tuple(max(0, min(255, v + shade)) for v in s.C_FLOOR)
                lit   = tuple(min(255, v + 12) for v in base)
                pygame.draw.rect(surf, base, (x, y, T, T))
                for _ in range(6):                         # grana della pietra
                    d  = rng.randint(-9, 9)
                    gc = tuple(max(0, min(255, v + d)) for v in base)
                    pygame.draw.rect(surf, gc, (x + rng.randrange(2, T - 4), y + rng.randrange(2, T - 4), 2, 2))
                if rng.random() < 0.12:                    # crepa occasionale
                    cx, cy = x + rng.randrange(8, T - 8), y + rng.randrange(8, T - 8)
                    pygame.draw.line(surf, s.C_FLOOR_ALT, (cx, cy),
                                     (cx + rng.randint(-10, 10), cy + rng.randint(-10, 10)))
                # Fughe: chiare in alto/sinistra, scure in basso/destra → lastre in rilievo
                pygame.draw.line(surf, lit, (x, y), (x + T - 1, y))
                pygame.draw.line(surf, lit, (x, y), (x, y + T - 1))
                pygame.draw.line(surf, grout_dark, (x, y + T - 1), (x + T - 1, y + T - 1))
                pygame.draw.line(surf, grout_dark, (x + T - 1, y), (x + T - 1, y + T - 1))

        # Ombra alla base dei muri (ambient occlusion): più forte sotto i muri a nord
        ao = gfx.Surface((self.pixel_w, self.pixel_h), pygame.SRCALPHA)
        for r in range(self.rows):
            for c in range(self.cols):
                if self.tiles[r][c] == TILE_WALL:
                    continue
                x, y = c * T, r * T
                if self._is_wall(r - 1, c):
                    for i in range(20):
                        a = int(s.AO_ALPHA * (1 - i / 20) ** 2)
                        pygame.draw.line(ao, (0, 0, 0, a), (x, y + i), (x + T - 1, y + i))
                for side, dx in ((c - 1, 1), (c + 1, -1)):
                    if self._is_wall(r, side):
                        edge = x if dx == 1 else x + T - 1
                        for i in range(10):
                            a = int(s.AO_ALPHA * 0.6 * (1 - i / 10) ** 2)
                            pygame.draw.line(ao, (0, 0, 0, a), (edge + i * dx, y), (edge + i * dx, y + T - 1))
        surf.blit(ao, (0, 0))
        return surf

    def _draw_wall_block(self, surface, r: int, c: int, cam_x: int, cam_y: int):
        T, H   = s.TILE_SIZE, s.WALL_HEIGHT
        assets = AssetManager.get()
        sx, sy = c * T - cam_x, r * T - cam_y
        piece = self._wall_art.get((r, c))
        if piece is not None:                      # blocco di pietra dipinto (la parte di questa tile)
            top, top_area, face, face_area = piece
            surface.blit(top, (sx, sy - H), top_area)
            if face is not None:
                surface.blit(face, (sx, sy + T - H), face_area)
        else:
            v = (r * 7 + c * 13) % 101             # variante fissa per blocco
            surface.blit(assets.wall_top(v), (sx, sy - H))
            if not self._is_wall(r + 1, c):        # faccia frontale visibile
                surface.blit(assets.wall_face(v), (sx, sy + T - H))
        if (r, c) in self._torch_tiles:
            self._draw_torch(surface, sx, sy)

    def _draw_torch(self, surface, sx: int, sy: int):
        """Torcia sul muro a nord: ritaglio dipinto + luce tremolante."""
        T, H = s.TILE_SIZE, s.WALL_HEIGHT
        img, meta = AssetManager.get().torch()
        face_top = sy + T - H                      # inizio dei mattoni: combacia col ritaglio
        x0 = sx + T // 2 - img.get_width() // 2
        y0 = face_top - meta.get("face_y", 0)
        surface.blit(img, (x0, y0))
        t  = pygame.time.get_ticks() / 1000.0
        fl = 0.8 + 0.2 * math.sin(t * 15 + sx) * math.sin(t * 6.1 + sy)
        glow = AssetManager.get().torch_glow()
        g = pygame.transform.smoothscale(glow, (round(glow.get_width() * fl), round(glow.get_height() * fl)))
        surface.blit(g, g.get_rect(center=(sx + T // 2, y0 + 22)), special_flags=pygame.BLEND_RGB_ADD)

    def _draw_gate(self, surface, r: int, c: int, cam_x: int, cam_y: int):
        """Porta bloccata: cancello di ferro alto quanto un muro."""
        T, H   = s.TILE_SIZE, s.WALL_HEIGHT
        sx, sy = c * T - cam_x, r * T - cam_y
        top    = pygame.Rect(sx, sy - H, T, T)
        pygame.draw.rect(surface, (70, 24, 24), top)
        pygame.draw.rect(surface, (110, 36, 32), top, 2)
        pygame.draw.rect(surface, (40, 12, 14), (sx, sy + T - H, T, H))
        for bx in range(4, T, 9):
            pygame.draw.rect(surface, s.C_DOOR_LOCKED, (sx + bx, sy - H + 4, 4, T + H - 8))
            pygame.draw.line(surface, (200, 80, 70), (sx + bx, sy - H + 4), (sx + bx, sy + T - 6))

    def _draw_chest(self, surface, cam_x: int, cam_y: int):
        """Chest: visibile sempre (scura/bloccata finché la stanza non è liberata)."""
        chest_surf = AssetManager.get().chest_sprite()
        csx = self.pixel_w // 2 - cam_x - chest_surf.get_width() // 2
        csy = self.pixel_h // 2 - cam_y - chest_surf.get_height() // 2
        surface.blit(chest_surf, (csx, csy))
        if not self.cleared:
            lock_ov = gfx.Surface(chest_surf.get_size(), pygame.SRCALPHA)
            lock_ov.fill((0, 0, 0, 165))
            surface.blit(lock_ov, (csx, csy))

    def draw(self, surface: pygame.Surface, camera_offset: tuple = (0, 0),
             player=None, player_projectiles=()):
        cam_x, cam_y = camera_offset
        T      = s.TILE_SIZE
        assets = AssetManager.get()

        surface.blit(self._floor_surface(), (-cam_x, -cam_y))

        # Portale della stanza finale (solo dopo aver sconfitto il boss): è a terra
        if self.is_end and self.cleared:
            t   = pygame.time.get_ticks() / 1000.0
            pcx = self.pixel_w // 2 - cam_x
            pcy = self.pixel_h // 2 - cam_y
            pr  = int(22 + 6 * math.sin(t * 2.5))
            pygame.draw.circle(surface, (20, 75, 45),    (pcx, pcy), pr + 14)
            pygame.draw.circle(surface, (55, 170, 90),   (pcx, pcy), pr, 3)
            pygame.draw.circle(surface, (150, 235, 170), (pcx, pcy), pr // 2)
            pygame.draw.circle(surface, (220, 255, 230), (pcx, pcy), 5)

        show_chest  = self.has_chest and not self.chest_opened
        chest_base  = self.pixel_h // 2 + 12
        projectiles = list(self.enemy_projectiles) + list(player_projectiles)

        # ── Ombre a terra ──
        def shadow(x, y, w, h):
            surface.blit(assets.shadow(w, h), (round(x) - w // 2 - cam_x, round(y) - h // 2 - cam_y))

        if show_chest:
            shadow(self.pixel_w // 2 + 2, chest_base, 38, 12)
        for item in self.loot:
            shadow(item.rect.centerx, item.rect.bottom, 18, 7)
        for enemy in self.enemies:
            w = max(26, int(enemy.rect.width * 0.9))
            shadow(enemy.pos.x, enemy.rect.bottom - 3, w, w // 3)
        for proj in projectiles:
            shadow(proj.pos.x, proj.pos.y + 18, 12, 5)        # in volo: ombra più in basso
        if player is not None:
            k = player.jump_height / s.PLAYER_DODGE_JUMP        # in aria: ombra più piccola
            shadow(player.pos.x, player.rect.bottom - 3, round(38 - 12 * k), round(13 - 4 * k))

        for enemy in self.enemies:                      # ombre dei massi in arrivo, crateri
            if hasattr(enemy, "draw_floor_fx"):
                enemy.draw_floor_fx(surface, camera_offset)

        # ── Muri e personaggi ordinati per Y della base (a parità: prima i muri) ──
        drawables = []
        for r in range(self.rows):
            for c in range(self.cols):
                if self.tiles[r][c] == TILE_WALL:
                    drawables.append(((r + 1) * T, 0, self._draw_wall_block, (surface, r, c, cam_x, cam_y)))
        if self._locked:
            for r, c in self._door_tile_set:
                drawables.append(((r + 1) * T, 0, self._draw_gate, (surface, r, c, cam_x, cam_y)))
        for item in self.loot:
            drawables.append((item.rect.bottom, 1, item.draw, (surface, camera_offset)))
        if show_chest:
            drawables.append((chest_base, 1, self._draw_chest, (surface, cam_x, cam_y)))
        for enemy in self.enemies:
            drawables.append((enemy.rect.bottom, 1, enemy.draw, (surface, camera_offset)))
        for proj in projectiles:
            drawables.append((proj.pos.y + 12, 1, proj.draw, (surface, camera_offset)))
        if player is not None:
            drawables.append((player.rect.bottom, 1, player.draw, (surface, camera_offset)))
            decoy = getattr(player, "decoy", None)
            if decoy is not None:
                drawables.append((decoy.rect.bottom, 1, decoy.draw, (surface, camera_offset)))

        drawables.sort(key=lambda d: (d[0], d[1]))
        for _, _, fn, args in drawables:
            fn(*args)

        for enemy in self.enemies:                      # massi che cadono: sopra a tutto
            if hasattr(enemy, "draw_air_fx"):
                enemy.draw_air_fx(surface, camera_offset)

