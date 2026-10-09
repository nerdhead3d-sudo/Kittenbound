import math
import pygame
from game import particles
from game import equipment
import random
from game import settings as s
from game.asset_manager import AssetManager
from game.loot import Loot
from game.sound import play, voice
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
        water: bool = False,
    ):
        rt = room_type or s.ROOM_TYPE_NORMAL
        self.water:   set = set()     # tile (r, c) del canale: si cammina ma lenti
        self.bridges: set = set()     # tile del canale coperte da una grata: velocità normale
        self.flow:   dict = {}        # tile del canale -> direzione della corrente (dx, dy)
        self._wants_water = water
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
        self.bag_recovered = False
        self.merchant      = None     # mercante nascosto (vedi Dungeon._place_merchant)
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
        if self.has_chest:                              # il forziere è solido (chiuso o aperto)
            self.chest_rect = pygame.Rect(self.pixel_w // 2 - 21, self.pixel_h // 2 + 6, 42, 18)
            self._base_wall_rects  = self._base_wall_rects + [self.chest_rect]
            self._enemy_wall_rects = self._base_wall_rects + self._door_rects
            self.wall_rects        = self._base_wall_rects

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

        if self._wants_water:
            self._carve_channels()
        if self.room_type != s.ROOM_TYPE_BOSS:
            self._add_obstacles(tiles)
        self._carve_doors(tiles)
        return tiles

    def _carve_channels(self):
        """Canale largo 2 tile, orizzontale, verticale o a croce, lontano dal centro e dalle
        porte. Dove passa la strada tra le porte e il centro c'è una grata, più una a caso."""
        mid_r, mid_c = self.rows // 2, self.cols // 2
        kind = random.choice(("h", "v", "x"))
        r0 = random.choice((2, self.rows - 5))
        c0 = random.choice((3, self.cols - 5))
        if kind in ("h", "x"):
            band = [(r, c) for r in (r0, r0 + 1) for c in range(1, self.cols - 1)]
            self.water.update(band)
            fx = random.choice((-1, 1))                   # la corrente va verso uno dei due lati
            self.flow.update({cell: (fx, 0) for cell in band})
            # ponte in più: non sull'incrocio con l'altro canale (resterebbe largo 1 tile)
            extra = random.choice([c for c in range(3, self.cols - 4)
                                   if abs(c - mid_c) > 3 and (kind == "h" or not c0 - 2 <= c <= c0 + 1)])
            for c in (mid_c - 1, mid_c, extra, extra + 1):
                self.bridges.update({(r0, c), (r0 + 1, c)})
        if kind in ("v", "x"):
            band = [(r, c) for c in (c0, c0 + 1) for r in range(1, self.rows - 1)]
            self.water.update(band)
            fy = random.choice((-1, 1))
            self.flow.update({cell: (0, fy) for cell in band})   # all'incrocio vince il verticale
            extra = random.choice([r for r in range(2, self.rows - 3)
                                   if abs(r - mid_r) > 2 and (kind == "v" or not r0 - 2 <= r <= r0 + 1)])
            for r in (mid_r - 1, mid_r, extra, extra + 1):
                self.bridges.update({(r, c0), (r, c0 + 1)})
        if kind == "x":                               # all'incrocio dei due canali è acqua
            self.bridges -= {(r, c) for r in (r0, r0 + 1) for c in (c0, c0 + 1)}

    def in_water(self, x: float, y: float) -> bool:
        """Il punto (coordinate mondo) è nell'acqua del canale (non su una grata)?"""
        if not self.water:
            return False
        cell = (int(y // s.TILE_SIZE), int(x // s.TILE_SIZE))
        return cell in self.water and cell not in self.bridges

    def _add_obstacles(self, tiles: list):
        """Pilastri interni casuali, lontani dal centro (spawn player)."""
        cr, cc = self.rows // 2, self.cols // 2
        candidates = [
            (r, c)
            for r in range(2, self.rows - 2)
            for c in range(2, self.cols - 2)
            if (abs(r - cr) >= 3 or abs(c - cc) >= 3)
            and not any((r + dr, c + dc) in self.water for dr in (-1, 0, 1) for dc in (-1, 0, 1))
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

    def _draw_water_fx(self, surface, cam_x, cam_y, player):
        """Luccichii che scorrono sull'acqua e cerchi attorno a chi ci cammina dentro."""
        T = s.TILE_SIZE
        t = pygame.time.get_ticks() / 1000.0
        for (r, c), (dx, dy) in self.flow.items():
            if (r, c) in self.bridges:
                continue
            x0, y0 = c * T - cam_x, r * T - cam_y
            for k in range(2):
                # scie che seguono la corrente: la fase dipende dalla posizione lungo il canale,
                # così passano da una tile all'altra come un flusso continuo
                along = c if dx else r
                ph    = (t * 0.55 - along * 0.5 * (dx or dy) + k * 0.37 + (r * 3 + c * 5) % 7 * 0.05) % 1.0
                ph    = ph if (dx or dy) > 0 else 1.0 - ph
                ln    = 6 + round(4 * math.sin(t * 3 + r + c + k))
                side  = 13 + k * 20 + round(2 * math.sin(t * 1.7 + along + k))
                col   = (110 + 30 * k, 195, 165)
                if dx:
                    x = x0 + round(ph * (T - ln))
                    pygame.draw.line(surface, col, (x, y0 + side), (x + ln, y0 + side))
                else:
                    y = y0 + round(ph * (T - ln))
                    pygame.draw.line(surface, col, (x0 + side, y), (x0 + side, y + ln))
        bodies = list(self.enemies) + ([player] if player is not None else [])
        for b in bodies:
            if self.in_water(b.pos.x, b.rect.bottom - 4):
                ph = (t * 1.6 + id(b) % 7 * 0.13) % 1.0
                w  = round(28 + 22 * ph)
                rect = pygame.Rect(0, 0, w, round(w * 0.35))
                rect.center = (round(b.pos.x) - cam_x, b.rect.bottom - 4 - cam_y)
                pygame.draw.ellipse(surface, (150, 220, 190), rect, 1)

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
        for item in self.loot:                             # la sacca brilla anche al buio
            if item.loot_type == "bag":
                lights.append((round(item.pos.x), round(item.pos.y) - 8, s.BAG_LIGHT_RADIUS))
        for proj in self.enemy_projectiles:                # proiettili in arrivo
            lights.append((round(proj.pos.x), round(proj.pos.y), 48))
        if self.merchant is not None and self.merchant.revealed:   # la lanterna del mercante
            lights.append(self.merchant.light())
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
            if self.tiles[r][c] == TILE_FLOOR and (r, c) not in self.water
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
        for e in list(self.enemies):                  # Unghie Seghettate: danno nel tempo
            if getattr(e, "bleed_t", 0) > 0 and e.alive:
                e.bleed_t  -= dt
                e.bleed_acc = getattr(e, "bleed_acc", 0.0) + s.BLEED_DPS * dt
                if e.bleed_acc >= 1:
                    dmg, e.bleed_acc = int(e.bleed_acc), e.bleed_acc % 1
                    e.take_damage(dmg, pierce=True)
                    if not e.alive:
                        self._on_enemy_killed(e, player)
        self.fx = [[x, y, age + dt] for x, y, age in getattr(self, "fx", []) if age + dt < 0.45]
        particles.update(self, dt)
        if self.water:                                # canali: in acqua si va piano
            stray = equipment.has(player, "collar_stray")
            player.terrain_mult = s.WATER_SLOW if (not stray and self.in_water(player.pos.x, player.rect.bottom - 4)) else 1.0
            for e in self.enemies:
                e.terrain_mult = s.WATER_SLOW if self.in_water(e.pos.x, e.rect.bottom - 4) else 1.0
        else:
            player.terrain_mult = 1.0
        if self.merchant is not None:                 # stanza liberata: il mercante esce dall'ombra
            if self.cleared and not self.merchant.revealed:
                self.merchant.reveal()
            self.merchant.update(dt)
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
                    enemy.take_damage(round(proj.damage * player.damage_mult),
                                      pierce=getattr(proj, 'reflected', False))
                    particles.burst(self, proj.pos.x, proj.pos.y, "hit")
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
            player.add_audacia(s.AUDACIA_PER_ROOM)
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
                elif item.loot_type == "bag":           # la sacca persa morendo
                    player.gold += item.value
                    player.say(f"Sacca recuperata: {item.value} oro", (250, 210, 80))
                    play("chest", 0.9)
                    play("coin", 0.8)
                    self.bag_recovered = True
                item.kill()

        # Apertura chest (solo dopo aver liberato la stanza)
        if self.has_chest and self.cleared and not self.chest_opened:
            cx, cy = self.chest_rect.center                # basta arrivarci accanto
            if player.pos.distance_to((cx, cy)) <= s.CHEST_OPEN_RADIUS:
                self.chest_opened = True
                self._open_chest(player)
                play("chest", 0.9)
                voice("cat_happy", 0.7, 0.5)

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
        from game import feel
        particles.burst(self, enemy.pos.x, enemy.rect.centery, "boss" if enemy.ENEMY_TYPE == "boss" else "death")
        if enemy.ENEMY_TYPE == "boss":                       # boss abbattuto: colpo pesante
            feel.hitstop(0.25)
            feel.shake(1.0)
        else:
            feel.hitstop(0.035)
            feel.shake(0.12)
        gold = round(random.randint(s.GOLD_DROP_MIN, s.GOLD_DROP_MAX) * s.COIN_VALUE
                     * self._reward_mult * player.gold_mult)
        self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "coin", gold))
        orbs = player.audacia >= s.AUDACIA_TIER_ORBS          # Audacia 10: più pallini rossi
        if random.random() < s.ORB_DROP_CHANCE + (s.AUDACIA_ORB_BONUS if orbs else 0):
            for _ in range(random.randint(1, s.ORB_DROP_MAX + (1 if orbs else 0))):
                off = pygame.math.Vector2(random.uniform(14, 30), 0).rotate(random.uniform(0, 360))
                self.loot.add(Loot(enemy.pos.x + off.x, enemy.pos.y + off.y, "orb", s.ORB_HEAL))
        roll = random.random()
        if roll < s.POTION_HP_CHANCE:
            self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "hp", s.POTION_HP_VALUE))
        elif roll < s.POTION_HP_CHANCE + s.POTION_EN_CHANCE:
            self.loot.add(Loot(enemy.pos.x, enemy.pos.y, "mp", s.POTION_ENERGY_VALUE))

    def _open_chest(self, player):
        tier = self.chest_tier
        if player.audacia >= s.AUDACIA_TIER_CHEST:  # Audacia 5: forziere di livello superiore
            tier = min(3, tier + 1)
        mult = self._reward_mult * player.gold_mult
        if tier == 3:                               # boss
            player.gold += round(s.CHEST_BOSS_GOLD * mult)
            player.hp     = float(player.hp_max)
            player.energy = float(player.energy_max)
        elif tier == 2:                             # stanza speciale
            player.gold += round(s.CHEST_SPECIAL_GOLD * mult)
            player.heal(s.POTION_HP_VALUE)
            player.restore_energy(s.POTION_ENERGY_VALUE)
        if tier == 3 or (self.room_type == s.ROOM_TYPE_BOSS):  # boss: sempre un oggetto
            weights = dict(s.EQUIP_BOSS_WEIGHTS)
            if player.audacia >= s.AUDACIA_TIER_RARE:
                weights[3] = weights.get(3, 0) + 30
            item = equipment.roll(player, weights)
            if item:
                equipment.give(player, item)
        elif random.random() < s.EQUIP_SPECIAL_CHANCE:  # stanza speciale: di rado
            item = equipment.roll(player, {1: 70, 2: 30})
            if item:
                equipment.give(player, item)
        if player.audacia >= s.AUDACIA_TIER_RARE:   # Audacia 15: potenziamento gratis
            kind = random.choice(("hp_max", "energy_max", "melee_dmg", "hp_regen"))
            if kind == "hp_max":
                player.hp_max += s.UPGRADE_HP_MAX_AMOUNT
                player.hp     += s.UPGRADE_HP_MAX_AMOUNT
                name = f"+{s.UPGRADE_HP_MAX_AMOUNT} HP max"
            elif kind == "energy_max":
                player.energy_max += s.UPGRADE_ENERGY_MAX_AMOUNT
                name = f"+{s.UPGRADE_ENERGY_MAX_AMOUNT} energia max"
            elif kind == "melee_dmg":
                player.melee_damage_bonus += s.UPGRADE_MELEE_DMG_AMOUNT
                name = f"+{s.UPGRADE_MELEE_DMG_AMOUNT} danno"
            else:
                player.hp_regen_bonus += s.UPGRADE_HP_REGEN_AMOUNT
                name = f"+{s.UPGRADE_HP_REGEN_AMOUNT} rigenerazione HP"
            player.say(f"Tesoro raro: {name}", (255, 215, 90))
            play("level_up", 0.7)

    def apply_single_damage(self, enemy, amount: int, player, pierce: bool = False):
        """Danno diretto a un singolo nemico (artiglio del balzo, contrattacco)."""
        if enemy not in self.enemies:
            return
        was_alive = enemy.alive
        enemy.take_damage(round(amount * player.damage_mult), pierce=pierce)
        particles.burst(self, enemy.pos.x, enemy.rect.centery, "crit")
        play("claw_heavy")
        if was_alive and not enemy.alive:
            self._on_enemy_killed(enemy, player)

    def shockwave(self, x: float, y: float, damage: int, player):
        """Artigli d'Ossidiana: il critico esplode e colpisce tutti i nemici vicini."""
        self.fx = getattr(self, "fx", []) + [[x, y, 0.0]]
        for enemy in list(self.enemies):
            if (enemy.pos - pygame.math.Vector2(x, y)).length() <= s.OBSIDIAN_RADIUS and enemy.alive:
                enemy.take_damage(round(damage * s.OBSIDIAN_MULT * player.damage_mult))
                if not enemy.alive:
                    self._on_enemy_killed(enemy, player)
        play("boss_smash", 0.5)
        from game import feel
        feel.shake(0.4)

    def apply_melee(self, hitbox: pygame.Rect, damage: int, player):
        """Applica danno melee a tutti i nemici nel hitbox."""
        hit_any = False
        for enemy in list(self.enemies):
            if not hitbox.colliderect(enemy.rect):
                continue
            hit_any   = True
            was_alive = enemy.alive
            enemy.take_damage(round(damage * player.damage_mult))
            hx = (hitbox.centerx + enemy.rect.centerx) / 2
            hy = (hitbox.centery + enemy.rect.centery) / 2
            particles.burst(self, hx, hy, "crit" if getattr(player, "_last_hit_crit", False) else "hit")
            if equipment.has(player, "claws_serrated") and enemy.alive:   # sanguina
                enemy.bleed_t = s.BLEED_TIME
            if was_alive and not enemy.alive:
                self._on_enemy_killed(enemy, player)
        if hit_any:
            play("hit", 0.9)

    def _find_spawn_near(self, hint_x: float, hint_y: float) -> tuple:
        """Trova il tile percorribile più vicino a (hint_x, hint_y)."""
        best, best_d2 = (hint_x, hint_y), float('inf')
        for r in range(1, self.rows - 1):
            for c in range(1, self.cols - 1):
                if self.tiles[r][c] == TILE_FLOOR and (r, c) not in self.water:
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
        rng  = random.Random(self.cols * 1000 + self.rows * 37 + sum(sum(row) for row in self.tiles))
        grout_dark = (58, 51, 45)
        dark, light = AssetManager.get().floor_tiles()   # piastrelle dalla stanza dipinta
        water_h, water_v, grate_h, grate_v = AssetManager.get().water_tiles()
        for r in range(self.rows):
            for c in range(self.cols):
                if self.tiles[r][c] == TILE_WALL:
                    continue
                x, y  = c * T, r * T
                if (r, c) in self.water:                 # canale: acqua, grate sui ponti
                    if (r, c) in self.bridges and (grate_h or grate_v):
                        # canale orizzontale = acqua a destra o sinistra fuori dal ponte
                        horiz = any((r, c + d) in self.water and (r, c + d) not in self.bridges for d in (-2, -1, 1, 2))
                        pool  = (grate_h if horiz else grate_v) or grate_h or grate_v
                        surf.blit(rng.choice(pool), (x, y))
                    elif water_h:                         # texture orientata come la corrente
                        vertical = self.flow.get((r, c), (1, 0))[1] != 0
                        surf.blit(rng.choice(water_v if vertical else water_h), (x, y))
                    else:
                        pygame.draw.rect(surf, (40, 80, 64), (x, y, T, T))
                    continue
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
        am = AssetManager.get()
        if self.chest_opened:
            chest_surf = am.chest_sprite(opened=True)
        else:
            chest_surf = am.chest_sprite() if self.cleared else am.chest_locked_sprite()
        if chest_surf is None:
            return
        # appoggiato a terra: la base sta sempre nello stesso punto, il coperchio aperto sale
        bx, by = self.pixel_w // 2 - cam_x, self.pixel_h // 2 + 24 - cam_y
        if not hasattr(Room, "_chest_shadow"):            # ombra di contatto, scura e larga
            sh = gfx.Surface((72, 24), pygame.SRCALPHA)
            for k in range(12, 0, -1):
                pygame.draw.ellipse(sh, (0, 0, 0, round(200 * (1 - k / 13) ** 0.6)),
                                    (36 - 3 * k, 12 - k, 6 * k, 2 * k))
            Room._chest_shadow = sh
        surface.blit(Room._chest_shadow, (bx - 36, by - 18))
        r = chest_surf.get_rect(midbottom=(bx, by))
        surface.blit(chest_surf, r)

    def draw(self, surface: pygame.Surface, camera_offset: tuple = (0, 0),
             player=None, player_projectiles=()):
        cam_x, cam_y = camera_offset
        T      = s.TILE_SIZE
        assets = AssetManager.get()

        surface.blit(self._floor_surface(), (-cam_x, -cam_y))
        if self.water:
            self._draw_water_fx(surface, cam_x, cam_y, player)

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

        show_chest  = self.has_chest and (not self.chest_opened
                                          or AssetManager.get().chest_sprite(opened=True) is not None)
        chest_base  = self.pixel_h // 2 + 12
        projectiles = list(self.enemy_projectiles) + list(player_projectiles)

        # ── Ombre a terra ──
        def shadow(x, y, w, h):
            surface.blit(assets.shadow(w, h), (round(x) - w // 2 - cam_x, round(y) - h // 2 - cam_y))

        if show_chest:
            shadow(self.pixel_w // 2 + 2, chest_base + 10, 58, 16)
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
        if self.merchant is not None and self.merchant.revealed:
            drawables.append((self.merchant.pos.y, 1, self.merchant.draw, (surface, camera_offset, player)))
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
        particles.draw(self, surface, camera_offset)
        for x, y, age in getattr(self, "fx", []):        # onda viola dell'Ossidiana
            k = age / 0.45
            r = round(20 + (s.OBSIDIAN_RADIUS - 20) * k)
            pygame.draw.circle(surface, (170, 110, 255), (round(x) - cam_x, round(y) - cam_y), r, max(1, round(5 * (1 - k))))
        for e in self.enemies:                           # gocce di chi sanguina
            if getattr(e, "bleed_t", 0) > 0:
                t = pygame.time.get_ticks() / 1000.0
                for k in range(2):
                    ph = (t * 1.8 + k * 0.5) % 1.0
                    pygame.draw.circle(surface, (200, 30, 40),
                                       (round(e.pos.x) - cam_x + (k * 10 - 5), round(e.pos.y) - cam_y - 20 + round(ph * 22)), 2)

