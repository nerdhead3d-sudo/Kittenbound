import heapq
import math
import pygame
import random
from game import settings as s
from game.asset_manager import AssetManager


class Enemy(pygame.sprite.Sprite):
    """
    Classe base per tutti i nemici.
    Macchina a stati: IDLE → CHASE → ATTACK.

    In CHASE usa A* sulla tile grid per aggirare gli ostacoli.
    Le sottoclassi sovrascrivono _do_attack() per comportamenti ranged.
    """

    # ── Statistiche (override nelle sottoclassi) ──────────────────────────────
    ENEMY_TYPE      = "base"
    HP              = 30
    SPEED           = 80
    DAMAGE          = 10
    XP              = 15
    ATTACK_RANGE    = s.ENEMY_ATTACK_RANGE
    ATTACK_COOLDOWN = s.ENEMY_ATTACK_COOLDOWN

    def __init__(self, x: float, y: float):
        super().__init__()
        assets      = AssetManager.get()
        self.image  = assets.enemy_sprite(self.ENEMY_TYPE)
        self._anims = assets.enemy_animations(self.ENEMY_TYPE)
        self.pos    = pygame.math.Vector2(x, y)
        # Hitbox fissa: indipendente dalla dimensione dello sprite
        self.rect   = pygame.Rect(0, 0, s.ENEMY_HITBOX_SIZE, s.ENEMY_HITBOX_SIZE)
        self.rect.center = (int(x), int(y))

        # Animazione
        self._facing       = pygame.math.Vector2(0, 1)
        self._last_move_ms = -1000     # ultimo spostamento reale (per scegliere la camminata)
        self._recover      = 0.0       # > 0: frame dopo il colpo (accompagnamento)

        self.hp     = self.HP
        self.hp_max = self.HP
        self.damage_reduction = 0.0   # 0.0 = nessuna riduzione; settato dallo Stregone

        self._attack_timer = random.uniform(0, self.ATTACK_COOLDOWN)
        self._wander_timer = 0.0
        self._wander_dir   = pygame.math.Vector2(1, 0).rotate(random.uniform(0, 360))
        self._state        = "idle"
        self._windup       = 0.0   # > 0: telegraph in corso prima del colpo
        self._hit_flash    = 0.0   # > 0: flash bianco dopo aver ricevuto danno

        # Pathfinding
        self._path: list         = []
        self._path_target        = None
        self._path_timer: float  = 0.0
        self._tile_grid          = None

    # ── Proprietà ─────────────────────────────────────────────────────────────

    @property
    def alive(self) -> bool:
        return self.hp > 0

    # ── Danni ─────────────────────────────────────────────────────────────────

    def take_damage(self, amount: int):
        actual = max(1, int(amount * (1.0 - self.damage_reduction)))
        self.hp -= actual
        self._hit_flash = 0.10
        if self.hp <= 0:
            self.kill()

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float, player, wall_rects: list, projectile_group,
               tile_grid=None, room_enemies=None):
        self._tile_grid  = tile_grid
        self._hit_flash  = max(0.0, self._hit_flash - dt)
        self._recover    = max(0.0, self._recover - dt)

        if self._windup > 0:
            self._windup = max(0.0, self._windup - dt)
            if self._windup <= 0:
                dist = (player.pos - self.pos).length()
                if dist <= self.ATTACK_RANGE * 1.2:
                    player.take_damage(self.DAMAGE)
                self._attack_timer = self.ATTACK_COOLDOWN
                self._recover      = s.ENEMY_ATTACK_RECOVER
            self.rect.center = (round(self.pos.x), round(self.pos.y))
            return

        dist_vec = player.pos - self.pos
        dist     = dist_vec.length()

        # Transizioni di stato
        if dist < s.ENEMY_CHASE_RANGE:
            self._state = "chase"
        else:
            self._state = "idle"
        if dist < self.ATTACK_RANGE:
            self._state = "attack"

        # Azione corrente
        if self._state == "idle":
            self._do_idle(dt, wall_rects)
        elif self._state == "chase":
            self._do_chase(dt, player, dist_vec, dist, wall_rects)
        elif self._state == "attack":
            self._do_attack(dt, player, dist_vec, dist, wall_rects, projectile_group)

        self._attack_timer = max(0.0, self._attack_timer - dt)
        self._path_timer   = max(0.0, self._path_timer - dt)
        self.rect.center   = (round(self.pos.x), round(self.pos.y))

    # ── Comportamenti ─────────────────────────────────────────────────────────

    def _do_idle(self, dt: float, wall_rects: list):
        # Reset path quando il nemico è idle
        self._path        = []
        self._path_target = None

        self._wander_timer -= dt
        if self._wander_timer <= 0:
            self._wander_dir   = pygame.math.Vector2(1, 0).rotate(random.uniform(0, 360))
            self._wander_timer = random.uniform(1.0, 2.5)
        self._move(self._wander_dir * self.SPEED * 0.35 * dt, wall_rects)

    def _do_chase(self, dt: float, player, dist_vec: pygame.math.Vector2,
                  dist: float, wall_rects: list):
        """Insegue il player usando A* se la tile grid è disponibile."""
        # Quando è molto vicino o non c'è griglia usa il movimento diretto
        if self._tile_grid is None or dist <= s.TILE_SIZE * 1.5:
            if dist > 0:
                self._move(dist_vec.normalize() * self.SPEED * dt, wall_rects)
            return

        my_tile     = (int(self.pos.x // s.TILE_SIZE), int(self.pos.y // s.TILE_SIZE))
        player_tile = (int(player.pos.x // s.TILE_SIZE), int(player.pos.y // s.TILE_SIZE))

        # Ricalcola il percorso se scaduto o se il player si è spostato di tile
        if self._path_timer <= 0 or player_tile != self._path_target:
            self._path        = self._astar(my_tile, player_tile, self._tile_grid)
            self._path_target = player_tile
            self._path_timer  = 0.35

        if self._path:
            self._follow_path(dt, wall_rects)
        elif dist > 0:
            # Fallback: nessun percorso trovato → movimento diretto
            self._move(dist_vec.normalize() * self.SPEED * dt, wall_rects)

    def _follow_path(self, dt: float, wall_rects: list):
        """Avanza verso il prossimo waypoint del percorso A*."""
        if len(self._path) < 2:
            return

        next_col, next_row = self._path[1]
        target = pygame.math.Vector2(
            next_col * s.TILE_SIZE + s.TILE_SIZE // 2,
            next_row * s.TILE_SIZE + s.TILE_SIZE // 2,
        )
        to_target = target - self.pos

        if to_target.length() < s.TILE_SIZE * 0.45:
            self._path.pop(0)   # waypoint raggiunto
            return

        self._move(to_target.normalize() * self.SPEED * dt, wall_rects)

    def _do_attack(self, dt: float, player, dist_vec: pygame.math.Vector2,
                   dist: float, wall_rects: list, projectile_group):
        """Avanza verso il player e avvia il telegraph quando è a tiro."""
        if dist > self.ATTACK_RANGE * 0.8 and dist > 0:
            self._move(dist_vec.normalize() * self.SPEED * dt, wall_rects)

        if self._attack_timer <= 0 and dist <= self.ATTACK_RANGE:
            self._start_windup(dist_vec)

    def _start_windup(self, to_player: pygame.math.Vector2):
        self._windup = s.ENEMY_WINDUP_TIME
        if to_player.length_squared() > 0:
            self._facing = to_player.normalize()     # si gira verso il bersaglio

    # ── A* Pathfinding ────────────────────────────────────────────────────────

    @staticmethod
    def _astar(start: tuple, goal: tuple, tiles: list) -> list:
        """
        A* su griglia 4-connessa.
        tiles[row][col]: 0 = calpestabile, 1 = muro.
        Restituisce lista di (col, row) da start a goal inclusi,
        oppure lista vuota se non esiste percorso.
        """
        rows = len(tiles)
        cols = len(tiles[0]) if rows else 0

        def walkable(c: int, r: int) -> bool:
            return 0 <= c < cols and 0 <= r < rows and tiles[r][c] == 0

        if not walkable(*start) or not walkable(*goal):
            return []
        if start == goal:
            return [start]

        def h(a: tuple, b: tuple) -> int:
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        # (f, g, (col, row))
        open_heap = [(h(start, goal), 0, start)]
        came_from: dict  = {}
        g_score          = {start: 0}
        closed: set      = set()

        while open_heap:
            _, _, cur = heapq.heappop(open_heap)
            if cur in closed:
                continue
            closed.add(cur)

            if cur == goal:
                # Ricostruzione percorso
                path = []
                while cur in came_from:
                    path.append(cur)
                    cur = came_from[cur]
                path.append(start)
                path.reverse()
                return path

            cc, cr = cur
            for dc, dr in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nb = (cc + dc, cr + dr)
                if not walkable(nb[0], nb[1]) or nb in closed:
                    continue
                tg = g_score[cur] + 1
                if tg < g_score.get(nb, 10_000):
                    came_from[nb] = cur
                    g_score[nb]   = tg
                    heapq.heappush(open_heap, (tg + h(nb, goal), tg, nb))

        return []

    # ── Movimento con collisioni separate per asse ────────────────────────────

    def _move(self, delta: pygame.math.Vector2, wall_rects, face=None):
        """face: direzione da guardare (es. il player mentre si indietreggia);
        di default guarda dove si muove."""
        start = pygame.math.Vector2(self.pos)
        self._move_axes(delta, wall_rects)
        moved = self.pos - start
        if moved.length_squared() > 0.01:
            look = pygame.math.Vector2(face) if face is not None else moved
            if look.length_squared() > 0:
                self._facing = look.normalize()
            self._last_move_ms = pygame.time.get_ticks()

    def _move_axes(self, delta: pygame.math.Vector2, wall_rects):
        # Asse X
        self.pos.x += delta.x
        self.rect.centerx = round(self.pos.x)
        if wall_rects:
            for wall in wall_rects:
                if self.rect.colliderect(wall):
                    if delta.x > 0:
                        self.rect.right = wall.left
                    else:
                        self.rect.left  = wall.right
                    self.pos.x = float(self.rect.centerx)
                    break

        # Asse Y
        self.pos.y += delta.y
        self.rect.centery = round(self.pos.y)
        if wall_rects:
            for wall in wall_rects:
                if self.rect.colliderect(wall):
                    if delta.y > 0:
                        self.rect.bottom = wall.top
                    else:
                        self.rect.top    = wall.bottom
                    self.pos.y = float(self.rect.centery)
                    break

    # ── Draw ──────────────────────────────────────────────────────────────────

    def _direction_index(self) -> int:
        angle = math.degrees(math.atan2(self._facing.y, self._facing.x))
        return round(angle / 45) % 8

    def _current_frame(self) -> pygame.Surface:
        if not self._anims:
            return self.image
        d = self._direction_index()
        if "attack" in self._anims and (self._windup > 0 or self._recover > 0):
            frames = self._anims["attack"][d]
            strike = s.ENEMY_ATTACK_STRIKE
            if self._windup > 0:       # caricamento sincronizzato col telegraph
                frac = 1.0 - self._windup / s.ENEMY_WINDUP_TIME
                return frames[min(strike - 1, int(frac * strike))]
            frac = 1.0 - self._recover / s.ENEMY_ATTACK_RECOVER
            return frames[min(len(frames) - 1, strike + int(frac * (len(frames) - strike)))]
        moving = pygame.time.get_ticks() - self._last_move_ms < 150
        if moving and "walk" in self._anims:
            frames = self._anims["walk"][d]
            fps    = max(6.0, min(14.0, 12.0 * self.SPEED / 110))
            return frames[int(pygame.time.get_ticks() / 1000 * fps) % len(frames)]
        return self._anims["idle"][d][0]

    def draw(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        image = self._current_frame()
        dest  = image.get_rect(center=(round(self.pos.x) - camera_offset[0],
                                       round(self.pos.y) - camera_offset[1]))
        if self._hit_flash > 0:
            tinted = image.copy()   # solo RGB: la trasparenza dello sprite resta intatta
            tinted.fill((180, 180, 180), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(tinted, dest)
        else:
            surface.blit(image, dest)
        if self._windup > 0:
            cx    = round(self.pos.x) - camera_offset[0]
            cy    = round(self.pos.y) - camera_offset[1]
            frac  = 1.0 - self._windup / s.ENEMY_WINDUP_TIME
            r     = int(12 + self.ATTACK_RANGE * 0.65 * frac)
            g     = int(160 * (1.0 - frac))
            width = 0 if frac >= 0.85 else 3
            pygame.draw.circle(surface, (225, g, 25), (cx, cy), max(r, 1), width)


# ── Bosco Incantato — roster ──────────────────────────────────────────────────

class RattoGuardia(Enemy):
    """Soldato di linea della colonia. Aggredisce direttamente."""
    ENEMY_TYPE      = "mouse_warrior"
    HP              = 90
    SPEED           = 105
    DAMAGE          = 14
    XP              = 18
    ATTACK_RANGE    = 46
    ATTACK_COOLDOWN = 1.1


class RattoEsploratore(Enemy):
    """
    Fugge dal player invece di inseguirlo.
    Se sopravvive 4 secondi, suona l'allarme e richiama 2 guardie.
    Il player deve ucciderlo prima che l'allarme scatti.
    """
    ENEMY_TYPE = "mouse_archer"
    HP         = 25
    SPEED      = 148
    XP         = 15

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self._alarm_timer  = s.ESPLORATORE_ALARM_TIME
        self._alarmed      = False
        self._spawn_timer  = 0.0
        self._spawn_armed  = False
        self.pending_spawns: list = []

    def update(self, dt, player, wall_rects, projectile_group,
               tile_grid=None, room_enemies=None):
        self._tile_grid    = tile_grid
        self._attack_timer = max(0.0, self._attack_timer - dt)
        self._path_timer   = max(0.0, self._path_timer - dt)
        self._hit_flash    = max(0.0, self._hit_flash - dt)

        dist_vec = player.pos - self.pos
        dist     = dist_vec.length()

        # Waiting to spawn reinforcements
        if self._spawn_armed:
            self._spawn_timer -= dt
            if self._spawn_timer <= 0:
                for _ in range(2):
                    off = pygame.math.Vector2(1, 0).rotate(random.uniform(0, 360)) * 70
                    self.pending_spawns.append(
                        (RattoGuardia, self.pos.x + off.x, self.pos.y + off.y)
                    )
                self._spawn_armed = False
                self.hp = 0
                self.kill()
            return

        if dist < s.ENEMY_CHASE_RANGE:
            if not self._alarmed:
                # Flee away from player
                if dist > 0:
                    self._move(-(dist_vec / dist) * self.SPEED * dt, wall_rects)
                self._alarm_timer -= dt
                if self._alarm_timer <= 0:
                    self._alarmed   = True
                    self._spawn_armed = True
                    self._spawn_timer = s.ESPLORATORE_SPAWN_DELAY
            else:
                # Alarmed, slow retreat while waiting
                if dist > 0:
                    self._move(-(dist_vec / dist) * self.SPEED * 0.3 * dt, wall_rects)
        else:
            self._do_idle(dt, wall_rects)

        self.rect.center = (round(self.pos.x), round(self.pos.y))

    def draw(self, surface, camera_offset=(0, 0)):
        super().draw(surface, camera_offset)
        cx = round(self.pos.x) - camera_offset[0]
        cy = round(self.pos.y) - camera_offset[1]
        font = AssetManager.get().font(12, bold=True)

        if self._alarmed:
            t = pygame.time.get_ticks() / 140.0
            if int(t) % 2 == 0:
                lbl = font.render("!!", True, (240, 55, 55))
                surface.blit(lbl, lbl.get_rect(centerx=cx, bottom=cy - 40))
        elif self._alarm_timer < s.ESPLORATORE_ALARM_TIME:
            lbl = font.render("!", True, (230, 190, 45))
            surface.blit(lbl, lbl.get_rect(centerx=cx, bottom=cy - 40))
            # Shrinking countdown arc
            frac = self._alarm_timer / s.ESPLORATORE_ALARM_TIME
            pygame.draw.circle(surface, (220, 170, 40), (cx, cy - 46), 7, 2)
            pygame.draw.arc(surface, (240, 50, 50),
                            pygame.Rect(cx - 10, cy - 56, 20, 20),
                            math.pi / 2,
                            math.pi / 2 + (1.0 - frac) * math.pi * 2, 3)


class RattoLancia(Enemy):
    """
    Porta una lancia: range melee esteso.
    Mantiene distanza ottimale e indietreggia se il player si avvicina troppo.
    """
    ENEMY_TYPE      = "mouse_lancer"
    HP              = 110
    SPEED           = 72
    DAMAGE          = 20
    XP              = 22
    ATTACK_RANGE    = 90
    ATTACK_COOLDOWN = 1.35

    def _do_attack(self, dt, player, dist_vec, dist, wall_rects, projectile_group):
        if dist > self.ATTACK_RANGE * 1.1 and dist > 0:
            self._move(dist_vec.normalize() * self.SPEED * dt, wall_rects)
        elif dist < 55 and dist > 0:
            self._move(-dist_vec.normalize() * self.SPEED * 0.6 * dt, wall_rects, face=dist_vec)

        if self._attack_timer <= 0 and dist <= self.ATTACK_RANGE:
            self._start_windup(dist_vec)


class RattoStregone(Enemy):
    """
    Mago melee: si avvicina lentamente, colpisce a corto raggio.
    Dopo STREGONE_CHANNEL_DELAY secondi, entra in Canalizzazione:
    tutti i ratti nel raggio ricevono 75% di riduzione danno.
    La canalizzazione si interrompe se il player si avvicina o lo colpisce.
    """
    ENEMY_TYPE      = "mouse_mage"
    HP              = 65
    SPEED           = 55
    DAMAGE          = 15
    XP              = 28
    ATTACK_RANGE    = 88
    ATTACK_COOLDOWN = 2.1

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self._channel_timer = s.STREGONE_CHANNEL_DELAY
        self._channeling    = False

    def take_damage(self, amount: int):
        self._channeling = False   # interrupt channel on hit
        super().take_damage(amount)

    def update(self, dt, player, wall_rects, projectile_group,
               tile_grid=None, room_enemies=None):
        self._tile_grid    = tile_grid
        self._attack_timer = max(0.0, self._attack_timer - dt)
        self._path_timer   = max(0.0, self._path_timer - dt)
        self._hit_flash    = max(0.0, self._hit_flash - dt)
        self._recover      = max(0.0, self._recover - dt)

        dist_vec = player.pos - self.pos
        dist     = dist_vec.length()

        if self._channeling:
            # Break if player too close
            if dist <= s.STREGONE_BREAK_RANGE:
                self._channeling = False
                self._channel_timer = random.uniform(6.0, 10.0)
            else:
                # Apply damage reduction to nearby allies
                if room_enemies:
                    for ally in room_enemies:
                        if ally is self:
                            continue
                        ally_dist = (ally.pos - self.pos).length()
                        if ally_dist <= s.STREGONE_CHANNEL_RANGE:
                            ally.damage_reduction = s.STREGONE_DAMAGE_REDUCTION
            self.rect.center = (round(self.pos.x), round(self.pos.y))
            return

        # Normal: count down to next channel
        self._channel_timer -= dt
        if self._channel_timer <= 0:
            allies = [e for e in (room_enemies or []) if e is not self]
            if allies:
                self._channeling    = True
                self._channel_timer = random.uniform(8.0, 13.0)

        if self._windup > 0:
            self._windup = max(0.0, self._windup - dt)
            if self._windup <= 0:
                if dist <= self.ATTACK_RANGE * 1.2:
                    player.take_damage(self.DAMAGE)
                self._attack_timer = self.ATTACK_COOLDOWN
                self._recover      = s.ENEMY_ATTACK_RECOVER
            self.rect.center = (round(self.pos.x), round(self.pos.y))
            return

        # Melee approach: avanza se lontano, arretra se troppo vicino
        if dist > self.ATTACK_RANGE * 0.8 and dist > 0:
            self._move(dist_vec.normalize() * self.SPEED * dt, wall_rects)
        elif dist < 45 and dist > 0:
            self._move(-dist_vec.normalize() * self.SPEED * dt, wall_rects, face=dist_vec)

        if self._attack_timer <= 0 and dist <= self.ATTACK_RANGE:
            self._start_windup(dist_vec)

        self.rect.center = (round(self.pos.x), round(self.pos.y))

    def draw(self, surface, camera_offset=(0, 0)):
        super().draw(surface, camera_offset)
        if self._channeling:
            cx = round(self.pos.x) - camera_offset[0]
            cy = round(self.pos.y) - camera_offset[1]
            t  = pygame.time.get_ticks() / 1000.0
            pr = int(36 + 6 * math.sin(t * 4.0))
            pygame.draw.circle(surface, (110, 60, 195), (cx, cy), pr, 3)
            pygame.draw.circle(surface, (160, 100, 240), (cx, cy), pr // 2, 2)
            pygame.draw.circle(surface, (80, 45, 150),
                               (cx, cy), int(s.STREGONE_CHANNEL_RANGE * 0.28), 1)
            font = AssetManager.get().font(12)
            lbl  = font.render("Canalizzazione!", True, (175, 125, 255))
            surface.blit(lbl, lbl.get_rect(centerx=cx, bottom=cy - 42))


class RattoSoldato(Enemy):
    """
    Lento e coriaceo. Al 50% HP entra in frenesia e aumenta la velocità.
    Forte sinergia con lo Stregone: quasi invulnerabile mentre è protetto.
    """
    ENEMY_TYPE      = "skeleton"
    HP              = 120
    SPEED           = 58
    DAMAGE          = 25
    XP              = 32
    ATTACK_RANGE    = 50
    ATTACK_COOLDOWN = 1.75
    _FRENZY_SPEED   = 108

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self._frenzied = False

    def update(self, dt, player, wall_rects, projectile_group,
               tile_grid=None, room_enemies=None):
        if not self._frenzied and self.hp / self.hp_max <= 0.5:
            self._frenzied      = True
            self.SPEED          = self._FRENZY_SPEED
            self.ATTACK_COOLDOWN = 1.1
        super().update(dt, player, wall_rects, projectile_group, tile_grid, room_enemies)

    def draw(self, surface, camera_offset=(0, 0)):
        super().draw(surface, camera_offset)
        if self._frenzied:
            cx = round(self.pos.x) - camera_offset[0]
            cy = round(self.pos.y) - camera_offset[1]
            pygame.draw.circle(surface, (215, 75, 30), (cx, cy), 20, 2)


# ── Boss ──────────────────────────────────────────────────────────────────────

class TopoArmaturato(Enemy):
    """
    Boss del Bosco Incantato.

    Fasi: patrol → windup → charging → stunned → (rage se HP ≤ 30%)
    • Quasi invulnerabile (90% riduzione danno) tranne durante lo stordimento.
    • Lo stordimento si attiva solo schivando la sua Carica Corazzata.
    • In Rage: cariche più veloci, finestra di stordimento ridotta, finte.
    """
    ENEMY_TYPE      = "boss"
    HP              = s.BOSS_HP
    SPEED           = s.BOSS_SPEED_PATROL
    DAMAGE          = s.BOSS_DAMAGE_MELEE
    XP              = 100
    ATTACK_RANGE    = 54
    ATTACK_COOLDOWN = 1.6

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.rect = pygame.Rect(0, 0, 52, 52)
        self.rect.center = (int(x), int(y))
        self._font_lbl   = AssetManager.get().font(13, bold=True)

        self._phase        = "patrol"
        self._rage         = False
        self._charge_dir   = pygame.math.Vector2(1, 0)
        self._timer        = 0.0
        self._is_feint     = False
        self._feint_done   = False
        self._charge_min_t = 0.0
        self._charge_cd    = 0.0
        self._charge_hit   = False
        self._sweep_cd        = 0.0
        self._sweep_dir       = pygame.math.Vector2(1, 0)
        self._sweep_hit       = False
        self._proximity_timer = 0.0

    def take_damage(self, amount: int):
        if self._phase != "stunned":
            amount = max(1, amount // 20)   # ~5% passa mentre è corazzato
        self.hp -= amount
        self._hit_flash = 0.10
        if self.hp <= 0:
            self.kill()

    def update(self, dt, player, wall_rects, projectile_group,
               tile_grid=None, room_enemies=None):
        self._attack_timer = max(0.0, self._attack_timer - dt)
        self._charge_min_t = max(0.0, self._charge_min_t - dt)
        self._charge_cd    = max(0.0, self._charge_cd - dt)
        self._sweep_cd     = max(0.0, self._sweep_cd - dt)
        self._hit_flash    = max(0.0, self._hit_flash - dt)
        self._recover      = max(0.0, self._recover - dt)

        if not self._rage and self.hp / self.hp_max <= s.BOSS_RAGE_THRESHOLD:
            self._rage = True

        if   self._phase == "patrol":
            self._do_patrol(dt, player, wall_rects)
        elif self._phase == "windup":
            self._do_windup(dt, player)
        elif self._phase == "feint_pause":
            self._do_feint_pause(dt, player)
        elif self._phase == "charging":
            self._do_charging(dt, player, wall_rects)
        elif self._phase == "stunned":
            self._do_stunned(dt)
        elif self._phase == "sweep_windup":
            self._do_sweep_windup(dt, player)
        elif self._phase == "sweep_active":
            self._do_sweep_active(dt, player)
        elif self._phase == "tail_spin":
            self._do_tail_spin(dt, player)

        self.rect.center = (round(self.pos.x), round(self.pos.y))

    def _do_patrol(self, dt, player, wall_rects):
        dist_vec = player.pos - self.pos
        dist     = dist_vec.length()
        spd      = s.BOSS_SPEED_PATROL * (1.4 if self._rage else 1.0)

        # Codata: proximity timer
        if dist < s.BOSS_PROXIMITY_RANGE:
            self._proximity_timer += dt
            if self._proximity_timer >= s.BOSS_PROXIMITY_TIME:
                self._proximity_timer = 0.0
                self._phase = "tail_spin"
                self._timer = s.BOSS_TAIL_DURATION
                return
        else:
            self._proximity_timer = 0.0

        if self._windup > 0:
            self._windup = max(0.0, self._windup - dt)
            if self._windup <= 0:
                if dist <= self.ATTACK_RANGE * 1.2:
                    player.take_damage(self.DAMAGE)
                self._attack_timer = self.ATTACK_COOLDOWN
                self._recover      = s.ENEMY_ATTACK_RECOVER
            return

        if dist > self.ATTACK_RANGE * 0.85:
            self._move(dist_vec.normalize() * spd * dt, wall_rects)

        # Colpo Spazzante: priorità sul melee base quando è a range e CD permette
        if dist <= s.BOSS_SWEEP_RANGE and self._sweep_cd <= 0:
            self._sweep_dir = dist_vec.normalize() if dist > 0 else self._sweep_dir
            self._sweep_cd  = s.BOSS_SWEEP_COOLDOWN
            self._sweep_hit = False
            self._phase     = "sweep_windup"
            self._timer     = s.BOSS_SWEEP_WINDUP
            return

        if self._attack_timer <= 0 and dist <= self.ATTACK_RANGE:
            self._start_windup(dist_vec)

        # Decide se caricare
        if dist <= 270 and dist > self.ATTACK_RANGE and self._charge_cd <= 0:
            self._charge_dir = (player.pos - self.pos).normalize()
            self._charge_hit = False
            if self._rage and random.random() < s.BOSS_FEINT_CHANCE:
                self._is_feint  = True
                self._feint_done = False
                self._timer     = s.BOSS_WINDUP_RAGE_TIME * 0.65
            else:
                self._is_feint = False
                self._timer    = s.BOSS_WINDUP_RAGE_TIME if self._rage else s.BOSS_WINDUP_TIME
            self._phase = "windup"

    def _do_windup(self, dt, player):
        self._timer -= dt
        if self._timer <= 0:
            if self._is_feint and not self._feint_done:
                self._phase = "feint_pause"
                self._timer = 0.38
            else:
                self._phase        = "charging"
                self._charge_min_t = 0.2

    def _do_feint_pause(self, dt, player):
        self._timer -= dt
        if self._timer <= 0:
            self._feint_done = True
            self._is_feint   = False
            self._charge_dir = (player.pos - self.pos).normalize()
            wt = (s.BOSS_WINDUP_RAGE_TIME * 0.55
                  if self._rage else s.BOSS_WINDUP_TIME * 0.55)
            self._timer = wt
            self._phase = "windup"

    def _do_charging(self, dt, player, wall_rects):
        intended = self._charge_dir * s.BOSS_CHARGE_SPEED * dt
        old_pos  = pygame.math.Vector2(self.pos)
        self._move(intended, wall_rects)

        # Danno al player durante la carica — una sola volta per passata
        if not player.invincible and not self._charge_hit and self.rect.colliderect(player.rect):
            player.take_damage(s.BOSS_DAMAGE_CHARGE)
            self._charge_hit = True

        # Rileva impatto con muro (solo dopo il grace period)
        if self._charge_min_t <= 0:
            actual_in_dir = (self.pos - old_pos).dot(self._charge_dir)
            if actual_in_dir < s.BOSS_CHARGE_SPEED * dt * 0.25:
                self._enter_stun()
                return
            # Controllo confini stanza (fallback)
            rw = s.BOSS_ROOM_COLS * s.TILE_SIZE
            rh = s.BOSS_ROOM_ROWS * s.TILE_SIZE
            if (self.pos.x <= s.TILE_SIZE * 2 or self.pos.x >= rw - s.TILE_SIZE * 2 or
                    self.pos.y <= s.TILE_SIZE * 2 or self.pos.y >= rh - s.TILE_SIZE * 2):
                self._enter_stun()

    def _enter_stun(self):
        stun_t      = s.BOSS_STUN_RAGE_DURATION if self._rage else s.BOSS_STUN_DURATION
        self._phase = "stunned"
        self._timer = stun_t

    def _do_stunned(self, dt):
        self._timer -= dt
        if self._timer <= 0:
            self._phase           = "patrol"
            self._attack_timer    = 1.5
            self._charge_cd       = 2.0 if self._rage else 3.0
            self._proximity_timer = 0.0

    def _do_sweep_windup(self, dt, player):
        dist_vec = player.pos - self.pos
        if dist_vec.length_squared() > 0:
            self._sweep_dir = dist_vec.normalize()
        self._timer -= dt
        if self._timer <= 0:
            self._phase     = "sweep_active"
            self._timer     = s.BOSS_SWEEP_ACTIVE
            self._sweep_hit = False

    def _do_sweep_active(self, dt, player):
        self._timer -= dt
        if not self._sweep_hit and self._sweep_hits_player(player):
            if player.take_damage(s.BOSS_SWEEP_DAMAGE):
                self._sweep_hit = True
        if self._timer <= 0:
            self._phase        = "patrol"
            self._attack_timer = 1.0

    def _sweep_hits_player(self, player) -> bool:
        to_player = player.pos - self.pos
        dist = to_player.length()
        if dist > s.BOSS_SWEEP_RANGE:
            return False
        if dist == 0:
            return True
        return to_player.normalize().dot(self._sweep_dir) >= 0.6

    def _do_tail_spin(self, dt, player):
        self._timer -= dt
        if self._timer <= 0:
            dist = (player.pos - self.pos).length()
            if dist <= s.BOSS_TAIL_RANGE:
                if player.take_damage(s.BOSS_TAIL_DAMAGE):
                    player.apply_stun(s.BOSS_TAIL_STUN)
            self._phase        = "patrol"
            self._attack_timer = 1.2

    def _boss_frame(self) -> "pygame.Surface | None":
        """Frame dello sprite in base alla fase del combattimento."""
        if not self._anims:
            return None
        anims, ticks = self._anims, pygame.time.get_ticks()
        if self._phase in ("windup", "charging"):
            self._facing = pygame.math.Vector2(self._charge_dir)
        elif self._phase in ("sweep_windup", "sweep_active"):
            self._facing = pygame.math.Vector2(self._sweep_dir)
        d = self._direction_index()

        if self._phase == "tail_spin":                       # codata: gira su se stesso
            return anims["idle"][(d + ticks // 45) % 8][0]
        if self._phase == "charging":                        # carica: corsa veloce
            frames = anims["walk"][d]
            return frames[(ticks // 45) % len(frames)]
        attack = anims.get("attack", anims["idle"])[d]
        if self._phase == "windup":                          # si prepara alla carica
            return attack[1]
        if self._phase == "sweep_windup":
            frac = 1.0 - self._timer / s.BOSS_SWEEP_WINDUP
            return attack[min(s.ENEMY_ATTACK_STRIKE - 1, int(frac * s.ENEMY_ATTACK_STRIKE))]
        if self._phase == "sweep_active":
            return attack[s.ENEMY_ATTACK_STRIKE + 1]
        if self._phase in ("stunned", "feint_pause"):
            return anims["idle"][d][0]
        return self._current_frame()                         # pattuglia: cammina / colpo base

    def draw(self, surface, camera_offset=(0, 0)):
        cx = round(self.pos.x) - camera_offset[0]
        cy = round(self.pos.y) - camera_offset[1]

        frame = self._boss_frame()
        if frame is not None:
            assets = AssetManager.get()
            if self._phase == "stunned":
                frame = assets.tinted(frame, (120, 150, 255))
            elif self._rage:
                frame = assets.tinted(frame, (255, 120, 110))
            if self._hit_flash > 0:
                frame = frame.copy()
                frame.fill((150, 140, 120), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(frame, frame.get_rect(center=(cx, cy)))
        else:
            self._draw_procedural_body(surface, cx, cy)

        self._draw_indicators(surface, cx, cy)

    def _draw_procedural_body(self, surface, cx, cy):
        """Fallback senza sprite: corpo disegnato con primitive."""
        if self._phase == "stunned":
            body_col, armor_col = (58, 78, 200), (88, 108, 230)
        elif self._rage:
            body_col, armor_col = (158, 32, 32), (200, 58, 38)
        else:
            body_col, armor_col = (66, 60, 74), (94, 86, 104)

        pygame.draw.circle(surface, body_col,  (cx, cy), 24)
        pygame.draw.circle(surface, armor_col, (cx, cy), 24, 5)
        pygame.draw.rect(surface, armor_col,
                         (cx - 14, cy - 8, 28, 10), border_radius=2)  # pettorale

        # Testa
        pygame.draw.circle(surface, (60, 48, 32),  (cx - 3, cy - 16), 14)
        pygame.draw.circle(surface, (0, 0, 0),     (cx - 3, cy - 16), 14, 2)
        pygame.draw.rect(surface, armor_col,
                         (cx - 13, cy - 21, 22, 6), border_radius=2)  # visiera
        pygame.draw.circle(surface, (62, 50, 32),  (cx - 12, cy - 26), 6)  # orecchi
        pygame.draw.circle(surface, (62, 50, 32),  (cx +  6, cy - 26), 6)
        eye_c = (240, 50, 50) if self._rage else (200, 60, 60)
        pygame.draw.circle(surface, eye_c, (cx - 7,  cy - 19), 3)
        pygame.draw.circle(surface, eye_c, (cx +  1,  cy - 19), 3)

        # Flash bianco quando riceve danno
        if self._hit_flash > 0:
            pygame.draw.circle(surface, (255, 240, 200), (cx, cy), 26, 4)

    def _draw_indicators(self, surface, cx, cy):
        """Telegraph degli attacchi, stordimento, aura e barra HP."""

        # Indicatore colpo melee (pattuglia)
        if self._phase == "patrol" and self._windup > 0:
            frac = 1.0 - self._windup / s.ENEMY_WINDUP_TIME
            r2   = int(28 + 24 * frac)
            gc   = int(140 * (1.0 - frac))
            pygame.draw.circle(surface, (225, gc, 25), (cx, cy), r2, 3)

        # Indicatore di carica (windup)
        if self._phase == "windup":
            is_fake = self._is_feint and not self._feint_done
            col = (235, 145, 25) if is_fake else (215, 50, 50)
            tip = (cx + int(self._charge_dir.x * 52),
                   cy + int(self._charge_dir.y * 52))
            pygame.draw.line(surface, col, (cx, cy), tip, 4)
            pygame.draw.circle(surface, col, tip, 8)
            pygame.draw.circle(surface, (255, 245, 200), tip, 4)

        # Pausa dopo finta (lampeggio giallo)
        elif self._phase == "feint_pause":
            t = pygame.time.get_ticks() / 160.0
            if int(t) % 2 == 0:
                pygame.draw.circle(surface, (235, 200, 45), (cx, cy), 34, 3)

        # Colpo Spazzante — telegraph
        elif self._phase == "sweep_windup":
            frac = 1.0 - self._timer / s.BOSS_SWEEP_WINDUP
            arc_r = int(s.BOSS_SWEEP_RANGE * min(frac + 0.1, 1.0))
            col = (220, 130, 30)
            sweep_angle = math.atan2(self._sweep_dir.y, self._sweep_dir.x)
            for offset in (-0.9, -0.45, 0.0, 0.45, 0.9):
                a  = sweep_angle + offset
                ex = cx + int(math.cos(a) * arc_r)
                ey = cy + int(math.sin(a) * arc_r)
                pygame.draw.line(surface, col, (cx, cy), (ex, ey), 2)
            pygame.draw.circle(surface, col, (cx, cy), int(10 * frac) + 8, 2)

        # Colpo Spazzante — hitbox attivo
        elif self._phase == "sweep_active":
            sweep_angle = math.atan2(self._sweep_dir.y, self._sweep_dir.x)
            for offset in (-0.9, -0.45, 0.0, 0.45, 0.9):
                a  = sweep_angle + offset
                ex = cx + int(math.cos(a) * s.BOSS_SWEEP_RANGE)
                ey = cy + int(math.sin(a) * s.BOSS_SWEEP_RANGE)
                pygame.draw.line(surface, (240, 80, 30), (cx, cy), (ex, ey), 5)

        # Codata
        elif self._phase == "tail_spin":
            frac  = 1.0 - self._timer / s.BOSS_TAIL_DURATION
            spin_r = int(s.BOSS_TAIL_RANGE * frac) + 10
            t_rot  = pygame.time.get_ticks() / 55.0
            pygame.draw.circle(surface, (230, 180, 40), (cx, cy), spin_r, 3)
            for i in range(4):
                a  = t_rot + i * math.pi / 2
                sx = cx + int(math.cos(a) * spin_r)
                sy = cy + int(math.sin(a) * spin_r)
                pygame.draw.circle(surface, (255, 220, 60), (sx, sy), 4)

        # Stelle di stordimento
        elif self._phase == "stunned":
            t = pygame.time.get_ticks() / 280.0
            for i in range(3):
                angle = t * 3.8 + i * (math.pi * 2 / 3)
                sx = cx + int(math.cos(angle) * 38)
                sy = cy + int(math.sin(angle) * 38) - 6
                pygame.draw.circle(surface, (255, 238, 75), (sx, sy), 5)
                pygame.draw.circle(surface, (255, 195, 25), (sx, sy), 3)

        # Aura rabbia
        if self._rage and self._phase not in ("stunned",):
            t  = pygame.time.get_ticks() / 1000.0
            ra = int(28 + 4 * math.sin(t * 5.0))
            pygame.draw.circle(surface, (175, 38, 18), (cx, cy), ra, 2)

        # Barra HP
        bw, bh = 112, 9
        bx, by = cx - bw // 2, cy - (66 if self._anims else 54)   # sopra lo sprite
        pct    = max(0.0, self.hp / self.hp_max)
        pygame.draw.rect(surface, (32, 28, 38), (bx - 1, by - 1, bw + 2, bh + 2))
        if pct > 0:
            bc = (198, 52, 38) if not self._rage else (218, 98, 28)
            pygame.draw.rect(surface, bc, (bx, by, int(bw * pct), bh))
        pygame.draw.rect(surface, (138, 128, 158), (bx, by, bw, bh), 1)
        # Soglia rabbia
        rx = bx + int(bw * s.BOSS_RAGE_THRESHOLD)
        pygame.draw.line(surface, (238, 118, 38), (rx, by - 2), (rx, by + bh + 2), 2)

        # Nome
        lbl = self._font_lbl.render("TOPO ARMATURATO", True, (178, 162, 195))
        surface.blit(lbl, lbl.get_rect(centerx=cx, bottom=by - 3))
