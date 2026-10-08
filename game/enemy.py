import heapq
import math
import pygame
import random
from game import settings as s
from game.asset_manager import AssetManager
from game.projectile import Projectile
from game.sound import play
from game import gfx



# ── Leggibilità degli attacchi (niente cerchi: si vede sul nemico) ─────────────

def warm_glow(frame: pygame.Surface, frac: float) -> pygame.Surface:
    """Il nemico si scalda di arancio mentre carica il colpo: più è acceso, più è vicino."""
    img = frame.copy()
    img.fill((round(150 * frac), round(70 * frac), round(10 * frac)), special_flags=pygame.BLEND_RGB_ADD)
    return img


TELL_NOW = 0.72        # ultima parte della carica: contorno bianco = "ORA!" (schiva / para)
_OUTLINE_CACHE: dict = {}


def tell_outline(frame: pygame.Surface, frac: float, thick: int = 3) -> "tuple[pygame.Surface, int]":
    """Contorno luminoso attorno alla sagoma del nemico durante la carica di un attacco.
    Arancio che si intensifica, poi bianco-giallo negli ultimi istanti (il momento di
    schivare o parare). Restituisce (superficie, margine) da centrare come lo sprite."""
    now   = frac >= TELL_NOW
    level = 9 if now else min(8, int(frac / TELL_NOW * 8))
    key   = (id(frame), level, thick)
    if key not in _OUTLINE_CACHE:
        if now:
            col = (255, 250, 200)
            t   = thick + 1
        else:
            k   = level / 8
            col = (255, round(120 + 60 * k), round(30 + 20 * k))
            t   = thick
        sil  = pygame.mask.from_surface(frame, 90).to_surface(setcolor=(*col, 255), unsetcolor=(0, 0, 0, 0))
        w, h = frame.get_size()
        out  = gfx.Surface((w + t * 2, h + t * 2), pygame.SRCALPHA)
        for dx in range(-t, t + 1):
            for dy in range(-t, t + 1):
                if dx * dx + dy * dy <= t * t:
                    out.blit(sil, (t + dx, t + dy))
        if len(_OUTLINE_CACHE) > 600:          # i frame sono pochi: la cache resta piccola
            _OUTLINE_CACHE.clear()
        _OUTLINE_CACHE[key] = (out, t)
    out, t = _OUTLINE_CACHE[key]
    if not now:                                 # tremolio di intensità mentre carica
        out = out.copy()
        out.set_alpha(round(140 + 115 * frac * (0.75 + 0.25 * math.sin(pygame.time.get_ticks() / 40))))
    return out, t


_GLINT_GLOW: dict = {}


def draw_glint(surface: pygame.Surface, x: int, y: int, frac: float, scale: float = 1.0):
    """Bagliore a stella sull'arma all'inizio della carica (classico segnale "sta per colpire")."""
    if frac > 0.55:
        return
    k = math.sin(frac / 0.55 * math.pi)
    r = round((8 + 16 * k) * scale)
    if r not in _GLINT_GLOW:                    # alone luminoso (somma di colore)
        g = gfx.Surface((r * 2, r * 2))
        for rr in range(r, 0, -2):
            f = (1 - rr / r) ** 2
            pygame.draw.circle(g, (round(255 * f), round(220 * f), round(140 * f)), (r, r), rr)
        _GLINT_GLOW[r] = g
    surface.blit(_GLINT_GLOW[r], (x - r, y - r), special_flags=pygame.BLEND_RGB_ADD)
    col = (255, 250, 215)
    w = max(2, round(3 * scale))
    pygame.draw.line(surface, col, (x - r, y), (x + r, y), w)
    pygame.draw.line(surface, col, (x, y - r), (x, y + r), w)
    d = round(r * 0.45)
    pygame.draw.line(surface, (255, 220, 140), (x - d, y - d), (x + d, y + d), 2)
    pygame.draw.line(surface, (255, 220, 140), (x - d, y + d), (x + d, y - d), 2)
    pygame.draw.circle(surface, (255, 255, 245), (x, y), max(2, round(3 * scale)))


def draw_protection_aura(surface: pygame.Surface, cx: int, cy: int, radius: int = 24):
    """Alone viola dei ratti protetti dallo Stregone."""
    t = pygame.time.get_ticks() / 1000.0
    r = radius + round(2 * math.sin(t * 5))
    layer = gfx.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
    pygame.draw.ellipse(layer, (150, 90, 255, 60), layer.get_rect().inflate(-2, -2))
    pygame.draw.ellipse(layer, (190, 140, 255, 170), layer.get_rect().inflate(-2, -2), 2)
    surface.blit(layer, layer.get_rect(center=(cx, cy + 4)))
    for i in range(3):                                   # scintille che girano
        a = t * 2.5 + i * math.tau / 3
        pygame.draw.circle(surface, (220, 190, 255),
                           (cx + round(math.cos(a) * r), cy + 4 + round(math.sin(a) * r * 0.6)), 2)


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
    RANGED          = False      # True: niente cerchio di telegraph melee

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
        self._windup_total = s.ENEMY_WINDUP_TIME
        self._hit_flash    = 0.0   # > 0: flash bianco dopo aver ricevuto danno
        self._aggro        = False # True: ti ha visto, ti insegue finché uno dei due muore
        self._bodies: list = []    # hitbox di altri nemici e del player (impostate dalla stanza)
        self._dmg_mult     = 1.0   # scaling per piano

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

    def take_damage(self, amount: int, pierce: bool = False):
        actual = max(1, int(amount * (1.0 - self.damage_reduction)))
        self.hp -= actual
        self._hit_flash = 0.10
        self._aggro     = True          # colpito da lontano: ora sa dove sei
        if self.hp <= 0:
            self.kill()
        else:
            play("squeak", 0.6)

    def scale_for_floor(self, floor: int):
        """Piani più profondi: nemici più resistenti, più forti e più remunerativi."""
        k = floor - 1
        self.hp = self.hp_max = int(self.HP * (1 + s.FLOOR_HP_SCALE * k))
        self._dmg_mult = 1 + s.FLOOR_DMG_SCALE * k
        self.DAMAGE    = int(type(self).DAMAGE * self._dmg_mult)
        self.XP        = int(type(self).XP * (1 + s.FLOOR_REWARD_SCALE * k))
        return self

    # ── Aggro ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _line_clear(a, b, wall_rects) -> bool:
        """True se nessun muro interrompe il segmento a→b (linea di vista)."""
        a, b = (round(a[0]), round(a[1])), (round(b[0]), round(b[1]))
        return not any(w.clipline(a, b) for w in wall_rects or ())

    def _update_aggro(self, player, dist: float, wall_rects, room_enemies):
        if self._aggro or dist > s.ENEMY_AGGRO_RANGE:
            return
        if self._line_clear(self.pos, player.pos, wall_rects):
            self._aggro = True
            for ally in room_enemies or ():                 # avvisa il branco
                if ally is not self and (ally.pos - self.pos).length() <= s.ENEMY_ALERT_RANGE:
                    ally._aggro = True

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
                    player.take_damage(self.DAMAGE, attacker=self)
                self._attack_timer = self.ATTACK_COOLDOWN
                self._recover      = s.ENEMY_ATTACK_RECOVER
                play("enemy_swing", 0.5)
            self.rect.center = (round(self.pos.x), round(self.pos.y))
            return

        dist_vec = player.pos - self.pos
        dist     = dist_vec.length()
        self._update_aggro(player, dist, wall_rects, room_enemies)

        # Transizioni di stato: con l'aggro ti insegue ovunque nella stanza
        if not self._aggro:
            self._state = "idle"
        elif dist < self.ATTACK_RANGE:
            self._state = "attack"
        else:
            self._state = "chase"

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

    def _start_windup(self, to_player: pygame.math.Vector2, duration: float = None):
        self._windup = self._windup_total = duration or s.ENEMY_WINDUP_TIME
        play("tell", 0.45)
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

    def _move(self, delta: pygame.math.Vector2, wall_rects, face=None, use_bodies=True):
        """face: direzione da guardare (es. il player mentre si indietreggia);
        di default guarda dove si muove. use_bodies: altri nemici e player sono solidi
        (si ignorano quelli già sovrapposti, così ci si può separare)."""
        start = pygame.math.Vector2(self.pos)
        blockers = wall_rects
        if use_bodies and self._bodies:
            blockers = list(wall_rects or ()) + [b for b in self._bodies
                                                 if b is not self.rect and not b.colliderect(self.rect)]
        self._move_axes(delta, blockers)
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
                frac = 1.0 - self._windup / self._windup_total
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
        cx = round(self.pos.x) - camera_offset[0]
        cy = round(self.pos.y) - camera_offset[1]
        if self.damage_reduction > 0:                  # protetto dallo Stregone
            draw_protection_aura(surface, cx, cy)
        image = self._current_frame()
        frac  = 1.0 - self._windup / self._windup_total if self._windup > 0 else None
        if frac is not None:
            image = warm_glow(image, frac)
        dest  = image.get_rect(center=(cx, cy))
        if frac is not None:                           # contorno: arancio → bianco = ORA
            outline, t = tell_outline(self._current_frame(), frac)
            surface.blit(outline, (dest.x - t, dest.y - t))
        if self._hit_flash > 0:
            tinted = image.copy()   # solo RGB: la trasparenza dello sprite resta intatta
            tinted.fill((180, 180, 180), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(tinted, dest)
        else:
            surface.blit(image, dest)
        if frac is not None:
            draw_glint(surface, cx + round(self._facing.x * 16), cy - 18 + round(self._facing.y * 8), frac)


# ── Bosco Incantato — roster ──────────────────────────────────────────────────

class RattoGuardia(Enemy):
    """Soldato di linea della colonia. Aggredisce direttamente."""
    ENEMY_TYPE      = "mouse_warrior"
    HP              = 90
    SPEED           = 128
    DAMAGE          = 15
    XP              = 18
    ATTACK_RANGE    = 46
    ATTACK_COOLDOWN = 0.9


class RattoEsploratore(Enemy):
    """
    Fugge dal player invece di inseguirlo.
    Se sopravvive 4 secondi, suona l'allarme e richiama 2 guardie.
    Il player deve ucciderlo prima che l'allarme scatti.
    """
    ENEMY_TYPE = "mouse_archer"
    HP         = 25
    SPEED      = 160
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
                play("reinforce", 0.8)
                self.hp = 0
                self.kill()
            return

        self._update_aggro(player, dist, wall_rects, room_enemies)
        if self._aggro:
            if not self._alarmed:
                # Flee away from player
                if dist > 0:
                    self._move(-(dist_vec / dist) * self.SPEED * dt, wall_rects)
                self._alarm_timer -= dt
                if self._alarm_timer <= 0:
                    self._alarmed   = True
                    play("alarm", 0.7)
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
        if self._alarmed:                              # allarme: onde rosse che pulsano
            t = (pygame.time.get_ticks() / 1000.0 * 2.5) % 1.0
            pygame.draw.circle(surface, (240, 60, 50), (cx, cy), round(18 + 30 * t), 2)
        elif self._alarm_timer < s.ESPLORATORE_ALARM_TIME:
            # Conto alla rovescia dell'allarme: arco che si chiude sopra la testa
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
    SPEED           = 92
    DAMAGE          = 20
    XP              = 22
    ATTACK_RANGE    = 90
    ATTACK_COOLDOWN = 1.15

    def _do_attack(self, dt, player, dist_vec, dist, wall_rects, projectile_group):
        if dist > self.ATTACK_RANGE * 1.1 and dist > 0:
            self._move(dist_vec.normalize() * self.SPEED * dt, wall_rects)
        elif dist < 55 and dist > 0:
            self._move(-dist_vec.normalize() * self.SPEED * 0.6 * dt, wall_rects, face=dist_vec)

        if self._attack_timer <= 0 and dist <= self.ATTACK_RANGE:
            self._start_windup(dist_vec)


class RattoStregone(Enemy):
    """
    Mago di supporto: finché è vivo protegge i ratti vicini (alone viola, subiscono
    molto meno danno) e un raggio lo collega a chi protegge. Resta dietro ai compagni.
    La protezione cade per qualche secondo se lo colpisci o gli stai addosso:
    va ucciso per primo.
    """
    ENEMY_TYPE      = "mouse_mage"
    HP              = 65
    SPEED           = 72
    DAMAGE          = 15
    XP              = 28
    ATTACK_RANGE    = 88
    ATTACK_COOLDOWN = 1.7

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self._interrupt  = 0.0
        self._channeling = False
        self._linked: list = []

    def take_damage(self, amount: int, pierce: bool = False):
        self._interrupt = s.STREGONE_INTERRUPT          # colpito: la protezione cade
        super().take_damage(amount, pierce)

    def update(self, dt, player, wall_rects, projectile_group,
               tile_grid=None, room_enemies=None):
        self._tile_grid    = tile_grid
        self._attack_timer = max(0.0, self._attack_timer - dt)
        self._path_timer   = max(0.0, self._path_timer - dt)
        self._hit_flash    = max(0.0, self._hit_flash - dt)
        self._recover      = max(0.0, self._recover - dt)
        self._interrupt    = max(0.0, self._interrupt - dt)

        dist_vec = player.pos - self.pos
        dist     = dist_vec.length()
        self._update_aggro(player, dist, wall_rects, room_enemies)
        if dist <= s.STREGONE_BREAK_RANGE:
            self._interrupt = max(self._interrupt, 0.4)

        # Protezione dei compagni vicini
        was = self._channeling
        self._linked = []
        if self._interrupt <= 0:
            for ally in room_enemies or ():
                if ally is not self and (ally.pos - self.pos).length() <= s.STREGONE_CHANNEL_RANGE:
                    ally.damage_reduction = s.STREGONE_DAMAGE_REDUCTION
                    self._linked.append(ally)
        self._channeling = bool(self._linked)
        if self._channeling and not was:
            play("channel", 0.5)

        if self._windup > 0:
            self._windup = max(0.0, self._windup - dt)
            if self._windup <= 0:
                if dist <= self.ATTACK_RANGE * 1.2:
                    player.take_damage(self.DAMAGE, attacker=self)
                self._attack_timer = self.ATTACK_COOLDOWN
                self._recover      = s.ENEMY_ATTACK_RECOVER
                play("enemy_swing", 0.5)
            self.rect.center = (round(self.pos.x), round(self.pos.y))
            return

        # Resta dietro ai compagni: si allontana se sei vicino, si avvicina se sei lontano
        near, far = s.STREGONE_KEEP_DIST
        if self._aggro and dist > 0:
            if dist < near and dist > self.ATTACK_RANGE * 0.9:
                self._move(-dist_vec.normalize() * self.SPEED * dt, wall_rects, face=dist_vec)
            elif dist > far:
                self._do_chase(dt, player, dist_vec, dist, wall_rects)
        elif not self._aggro:
            self._do_idle(dt, wall_rects)

        if self._attack_timer <= 0 and dist <= self.ATTACK_RANGE:
            self._start_windup(dist_vec)

        self.rect.center = (round(self.pos.x), round(self.pos.y))

    def draw(self, surface, camera_offset=(0, 0)):
        cx = round(self.pos.x) - camera_offset[0]
        cy = round(self.pos.y) - camera_offset[1]
        if self._channeling:
            t = pygame.time.get_ticks() / 1000.0
            for ally in self._linked:                      # raggi verso i protetti
                ax = round(ally.pos.x) - camera_offset[0]
                ay = round(ally.pos.y) - camera_offset[1]
                pts = []
                for k in range(9):
                    u = k / 8
                    wob = math.sin(u * math.pi * 3 + t * 9) * 4 * math.sin(u * math.pi)
                    nx, ny = -(ay - cy), (ax - cx)
                    ln = math.hypot(nx, ny) or 1
                    pts.append((cx + (ax - cx) * u + nx / ln * wob, cy - 10 + (ay - cy + 10) * u + ny / ln * wob))
                pygame.draw.lines(surface, (150, 100, 240), False, pts, 2)
            pr = int(30 + 5 * math.sin(t * 4.0))
            pygame.draw.circle(surface, (110, 60, 195), (cx, cy + 4), pr, 2)
            pygame.draw.circle(surface, (170, 120, 250), (cx, cy + 4), pr // 2, 1)
        super().draw(surface, camera_offset)


class RattoSoldato(Enemy):
    """
    Lento e coriaceo. Al 50% HP entra in frenesia e aumenta la velocità.
    Forte sinergia con lo Stregone: quasi invulnerabile mentre è protetto.
    """
    ENEMY_TYPE      = "skeleton"
    HP              = 120
    SPEED           = 78
    DAMAGE          = 25
    XP              = 32
    ATTACK_RANGE    = 50
    ATTACK_COOLDOWN = 1.45
    _FRENZY_SPEED   = 135

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self._frenzied = False

    def update(self, dt, player, wall_rects, projectile_group,
               tile_grid=None, room_enemies=None):
        if not self._frenzied and self.hp / self.hp_max <= 0.5:
            self._frenzied      = True
            play("frenzy", 0.8)
            self.SPEED          = self._FRENZY_SPEED
            self.ATTACK_COOLDOWN = 0.9
        super().update(dt, player, wall_rects, projectile_group, tile_grid, room_enemies)

    def draw(self, surface, camera_offset=(0, 0)):
        super().draw(surface, camera_offset)
        if self._frenzied:
            cx = round(self.pos.x) - camera_offset[0]
            cy = round(self.pos.y) - camera_offset[1]
            pygame.draw.circle(surface, (215, 75, 30), (cx, cy), 20, 2)


class RattoFromboliere(Enemy):
    """
    Tiratore: tiene le distanze e lancia sassi con la fionda.
    Carica il lancio per SLINGER_WINDUP secondi (senza mostrare dove mira); se ti avvicini
    indietreggia, a distanza media si sposta di lato per non stare fermo.
    Tira solo se vede il player (nessun muro in mezzo), altrimenti lo raggiunge.
    """
    ENEMY_TYPE      = "mouse_slinger"
    HP              = 55
    SPEED           = 100
    DAMAGE          = 12
    XP              = 24
    ATTACK_COOLDOWN = 1.6
    RANGED          = True

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self._strafe_dir   = random.choice((-1, 1))
        self._strafe_timer = random.uniform(1.0, 2.0)
        self._aim          = pygame.math.Vector2(0, 1)

    def update(self, dt, player, wall_rects, projectile_group,
               tile_grid=None, room_enemies=None):
        self._tile_grid    = tile_grid
        self._attack_timer = max(0.0, self._attack_timer - dt)
        self._path_timer   = max(0.0, self._path_timer - dt)
        self._hit_flash    = max(0.0, self._hit_flash - dt)
        self._recover      = max(0.0, self._recover - dt)

        dist_vec = player.pos - self.pos
        dist     = dist_vec.length()
        self._update_aggro(player, dist, wall_rects, room_enemies)

        if self._windup > 0:                       # sta mirando: resta fermo
            if dist > 0:
                self._aim = dist_vec.normalize()
                self._facing = pygame.math.Vector2(self._aim)
            self._windup = max(0.0, self._windup - dt)
            if self._windup <= 0:
                projectile_group.add(Projectile(
                    self.pos.x, self.pos.y - 10, self._aim, damage=self.DAMAGE,
                    owner="enemy", speed=s.SLINGER_PROJ_SPEED,
                    max_range=s.SLINGER_PROJ_RANGE, style="stone"))
                play("sling", 0.6)
                self._attack_timer = self.ATTACK_COOLDOWN
                self._recover      = s.ENEMY_ATTACK_RECOVER
            self.rect.center = (round(self.pos.x), round(self.pos.y))
            return

        if not self._aggro:
            self._do_idle(dt, wall_rects)
            self.rect.center = (round(self.pos.x), round(self.pos.y))
            return

        sees = self._line_clear(self.pos, player.pos, wall_rects)
        if not sees or dist > s.SLINGER_MAX_DIST:
            self._do_chase(dt, player, dist_vec, dist, wall_rects)
        elif dist < s.SLINGER_MIN_DIST and dist > 0:
            self._move(-dist_vec.normalize() * self.SPEED * dt, wall_rects, face=dist_vec)
        elif dist > 0:                              # distanza giusta: si sposta di lato
            self._strafe_timer -= dt
            if self._strafe_timer <= 0:
                self._strafe_dir   = -self._strafe_dir
                self._strafe_timer = random.uniform(1.0, 2.2)
            side = pygame.math.Vector2(-dist_vec.y, dist_vec.x).normalize() * self._strafe_dir
            before = pygame.math.Vector2(self.pos)
            self._move(side * self.SPEED * 0.55 * dt, wall_rects, face=dist_vec)
            if (self.pos - before).length_squared() < 0.01:   # contro un muro: cambia lato
                self._strafe_dir = -self._strafe_dir

        if sees and self._attack_timer <= 0 and dist <= s.SLINGER_PROJ_RANGE * 0.8:
            self._start_windup(dist_vec, s.SLINGER_WINDUP)
        self.rect.center = (round(self.pos.x), round(self.pos.y))


# ── Boss ──────────────────────────────────────────────────────────────────────

class TopoArmaturato(Enemy):
    """
    Boss del Bosco Incantato.

    Fasi: patrol → windup → charging → stunned → (rage se HP ≤ 30%)
    • Quasi invulnerabile (~95% riduzione danno) tranne durante lo stordimento.
    • Si stordisce quando la Carica Corazzata finisce contro un muro: va schivata
      (finestra di reazione breve) e fatta schiantare.
    • Se resti a distanza ti spara sfere di fuoco veloci (a ventaglio in Rage).
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
        self._proximity_timer = 0.0
        self._shot_cd         = 1.0
        self._rock_cd         = 4.0
        self._rocks: list     = []      # massi in arrivo: [pos, tempo, avviso, atterrato]
        self._knife_cd        = 2.0
        self._knife_dir       = pygame.math.Vector2(1, 0)
        self._knife_count     = s.BOSS_KNIFE_COUNT
        self._knife_total     = s.BOSS_KNIFE_WINDUP
        self._knife_ranged    = False   # True: tiro a distanza (3 coltelli, 5 in furia)

    def take_damage(self, amount: int, pierce: bool = False):
        if self._phase != "stunned":
            if not pierce:
                amount = max(1, amount // 20)   # ~5% passa mentre è corazzato (non i colpi parati)
        self.hp -= amount
        self._hit_flash = 0.10
        if self.hp <= 0:
            self.kill()
        else:
            play("squeak_big", 0.8)

    def update(self, dt, player, wall_rects, projectile_group,
               tile_grid=None, room_enemies=None):
        self._attack_timer = max(0.0, self._attack_timer - dt)
        self._charge_min_t = max(0.0, self._charge_min_t - dt)
        self._charge_cd    = max(0.0, self._charge_cd - dt)
        self._shot_cd      = max(0.0, self._shot_cd - dt)
        self._rock_cd      = max(0.0, self._rock_cd - dt)
        self._knife_cd     = max(0.0, self._knife_cd - dt)
        self._hit_flash    = max(0.0, self._hit_flash - dt)
        self._recover      = max(0.0, self._recover - dt)

        if not self._rage and self.hp / self.hp_max <= s.BOSS_RAGE_THRESHOLD:
            self._rage = True
            play("boss_roar")

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
        elif self._phase == "tail_spin":
            self._do_tail_spin(dt, player)
        elif self._phase == "slam":
            self._do_slam(dt, player)
        elif self._phase == "knife_windup":
            self._do_knife_windup(dt, player, projectile_group)

        self._update_rocks(dt, player)
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
                play("boss_tail")
                self._timer = s.BOSS_TAIL_DURATION
                return
        else:
            self._proximity_timer = 0.0

        if self._windup > 0:
            self._windup = max(0.0, self._windup - dt)
            if self._windup <= 0:
                if dist <= self.ATTACK_RANGE * 1.2:
                    player.take_damage(self.DAMAGE, attacker=self)
                self._attack_timer = self.ATTACK_COOLDOWN
                self._recover      = s.ENEMY_ATTACK_RECOVER
                play("boss_smash", 0.9)
            return

        if dist > self.ATTACK_RANGE * 0.85:
            self._move(dist_vec.normalize() * spd * dt, wall_rects)

        # Raffica di coltelli: ti sei avvicinato → li carica attorno a sé e li scaglia
        if dist <= s.BOSS_KNIFE_RANGE and self._knife_cd <= 0:
            self._start_knives(dist_vec, ranged=False)
            return

        if self._attack_timer <= 0 and dist <= self.ATTACK_RANGE:
            self._start_windup(dist_vec)

        # Pioggia di massi: pesta il terreno, i massi cadono attorno al gatto
        if self._rock_cd <= 0 and dist > 70:
            self._phase = "slam"
            self._timer = s.BOSS_SLAM_TIME
            self._facing = dist_vec.normalize() if dist > 0 else self._facing
            play("boss_growl", 0.7)
            return

        # Decide se caricare
        if dist <= s.BOSS_CHARGE_RANGE and dist > self.ATTACK_RANGE and self._charge_cd <= 0:
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
            play("boss_growl", 0.8)
            return

        # A distanza: ventaglio di coltelli
        if dist > s.BOSS_SHOT_MIN_DIST and self._shot_cd <= 0:
            self._start_knives(dist_vec, ranged=True)

    def _start_knives(self, to_player, ranged: bool):
        """Solleva i coltelli: raffica ravvicinata (5) o tiro a distanza (3, 5 in furia)."""
        if to_player.length_squared() > 0:
            self._knife_dir = to_player.normalize()
        self._facing       = pygame.math.Vector2(self._knife_dir)
        self._knife_ranged = ranged
        if ranged:
            self._knife_count = s.BOSS_SHOT_RAGE_COUNT if self._rage else s.BOSS_SHOT_COUNT
            self._knife_total = s.BOSS_SHOT_RAGE_WINDUP if self._rage else s.BOSS_SHOT_WINDUP
        else:
            self._knife_count = s.BOSS_KNIFE_COUNT
            self._knife_total = s.BOSS_KNIFE_RAGE_WINDUP if self._rage else s.BOSS_KNIFE_WINDUP
        self._phase = "knife_windup"
        self._timer = self._knife_total
        play("knife_draw", 0.8)

    def _knife_windup_total(self) -> float:
        return self._knife_total

    def _knife_positions(self) -> list:
        """Posizioni (x, y, altezza) dei coltelli che fluttuano attorno al boss durante la carica:
        si alzano dal corpo e si aprono a ventaglio alle sue spalle, puntati verso il gatto."""
        frac = 1.0 - self._timer / self._knife_windup_total()
        rise = min(1.0, frac / 0.4)
        ease = 1 - (1 - rise) ** 3
        base = math.degrees(math.atan2(self._knife_dir.y, self._knife_dir.x))
        shake_k = max(0.0, frac - 0.6) / 0.4                  # tremano poco prima di partire
        out = []
        for k in range(self._knife_count):
            off   = k - (self._knife_count - 1) / 2
            a     = math.radians(base + 180 + off * 40 * ease)
            r     = 14 + 44 * ease
            shake = math.sin(pygame.time.get_ticks() / 25 + k * 1.7) * 2.0 * shake_k
            out.append((self.pos.x + math.cos(a) * r + shake,
                        self.pos.y + math.sin(a) * r * 0.6,
                        24 + (36 - abs(off) * 6) * ease))
        return out

    def _do_knife_windup(self, dt, player, projectile_group):
        to_player = player.pos - self.pos
        if to_player.length_squared() > 0:                   # mira fino all'ultimo
            self._knife_dir = to_player.normalize()
            self._facing    = pygame.math.Vector2(self._knife_dir)
        self._timer -= dt
        if self._timer > 0:
            return
        count  = self._knife_count
        ranged = self._knife_ranged
        spread = s.BOSS_SHOT_SPREAD if ranged else s.BOSS_KNIFE_SPREAD
        damage = s.BOSS_SHOT_DAMAGE if ranged else s.BOSS_KNIFE_DAMAGE
        speed  = s.BOSS_SHOT_SPEED if ranged else s.BOSS_KNIFE_SPEED
        for k, (x, y, _z) in enumerate(self._knife_positions()):
            angle = (k - (count - 1) / 2) * spread
            projectile_group.add(Projectile(
                x, y, self._knife_dir.rotate(angle),
                damage=int(damage * self._dmg_mult), owner="enemy",
                speed=speed, max_range=900 if ranged else 700, style="knife"))
        play("knife_throw", 0.9)
        if ranged:
            self._shot_cd  = s.BOSS_SHOT_RAGE_COOLDOWN if self._rage else s.BOSS_SHOT_COOLDOWN
        else:
            self._knife_cd = s.BOSS_KNIFE_RAGE_COOLDOWN if self._rage else s.BOSS_KNIFE_COOLDOWN
        self._phase        = "patrol"
        self._attack_timer = max(self._attack_timer, 0.6)

    def _draw_knives(self, surface, cx, cy, behind: bool):
        """Coltelli sospesi durante la carica: puntati verso il gatto, contorno bianco = ORA."""
        if self._phase != "knife_windup":
            return
        frames = AssetManager.get().fx_frames("knife")
        frac   = 1.0 - self._timer / self._knife_windup_total()
        now    = frac >= TELL_NOW
        angle  = math.degrees(math.atan2(self._knife_dir.y, self._knife_dir.x)) % 360
        ox, oy = round(self.pos.x) - cx, round(self.pos.y) - cy
        for x, y, z in self._knife_positions():
            if (y < self.pos.y) != behind:
                continue
            sx, sy = round(x) - ox, round(y) - oy
            shadow = gfx.Surface((22, 8), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 70), shadow.get_rect())
            surface.blit(shadow, (sx - 11, sy + 14))
            ky = sy - round(z) + 18
            if frames:
                img = frames[round(angle / (360 / len(frames))) % len(frames)]
                outline, t = tell_outline(img, frac, thick=2)
                surface.blit(outline, outline.get_rect(center=(sx, ky)))
                surface.blit(img, img.get_rect(center=(sx, ky)))
            if now:                                            # scintilla sulla punta
                tip = self._knife_dir * 20
                pygame.draw.circle(surface, (255, 250, 220), (sx + round(tip.x), ky + round(tip.y)), 3)

    def _do_slam(self, dt, player):
        self._timer -= dt
        if self._timer > 0:
            return
        play("boss_smash", 0.9)
        count = s.BOSS_ROCK_RAGE_COUNT if self._rage else s.BOSS_ROCK_COUNT
        warn  = s.BOSS_ROCK_RAGE_WARN if self._rage else s.BOSS_ROCK_WARN
        rw, rh = s.BOSS_ROOM_COLS * s.TILE_SIZE, s.BOSS_ROOM_ROWS * s.TILE_SIZE
        margin = s.TILE_SIZE + 20
        spots  = [pygame.math.Vector2(max(margin, min(rw - margin, player.pos.x)),   # uno cade sempre dove sei
                                      max(margin, min(rh - margin, player.pos.y)))]
        tries  = 0
        while len(spots) < count and tries < 400:                # sparsi su tutta la stanza
            tries += 1
            pos = pygame.math.Vector2(random.uniform(margin, rw - margin), random.uniform(margin, rh - margin))
            if all((pos - o).length() >= s.BOSS_ROCK_MIN_GAP for o in spots):
                spots.append(pos)
        random.shuffle(spots)
        for k, pos in enumerate(spots):
            self._rocks.append([pos, -k * s.BOSS_ROCK_STAGGER, warn, False])
        play("rock_fall", 0.7)
        self._rock_cd = s.BOSS_ROCK_RAGE_COOLDOWN if self._rage else s.BOSS_ROCK_COOLDOWN
        self._phase   = "patrol"

    def _update_rocks(self, dt, player):
        for rock in self._rocks:
            rock[1] += dt
            if not rock[3] and rock[1] >= rock[2]:                # impatto
                rock[3] = True
                play("rock_impact", 0.9)
                if (player.pos - rock[0]).length() <= s.BOSS_ROCK_RADIUS + 14:
                    player.take_damage(int(s.BOSS_ROCK_DAMAGE * self._dmg_mult))
        self._rocks = [r for r in self._rocks if r[1] < r[2] + 0.6]

    def draw_floor_fx(self, surface, cam):
        """Ombre dei massi in arrivo (sul pavimento, sotto a tutto) e crateri."""
        for pos, t, warn, landed in self._rocks:
            x, y = round(pos.x) - cam[0], round(pos.y) - cam[1]
            if landed:
                k = (t - warn) / 0.6
                layer = gfx.Surface((90, 50), pygame.SRCALPHA)
                pygame.draw.ellipse(layer, (20, 16, 14, round(150 * (1 - k))), (5, 8, 80, 34))
                surface.blit(layer, (x - 45, y - 25))
                continue
            if t < 0:
                continue
            k = min(1.0, t / warn)                                # l'ombra cresce e si scurisce
            w, h = round(16 + 60 * k), round(8 + 30 * k)
            layer = gfx.Surface((w + 4, h + 4), pygame.SRCALPHA)
            pygame.draw.ellipse(layer, (0, 0, 0, round(60 + 130 * k)), (2, 2, w, h))
            surface.blit(layer, (x - w // 2 - 2, y - h // 2 - 2))

    def draw_air_fx(self, surface, cam):
        """Massi che cadono (sopra a tutto) e polvere dell'impatto."""
        rock_img = AssetManager.get().boulder()
        for pos, t, warn, landed in self._rocks:
            x, y = round(pos.x) - cam[0], round(pos.y) - cam[1]
            if landed:
                k = (t - warn) / 0.6
                for i in range(8):                                # polvere e schegge
                    a = i * math.tau / 8 + pos.x * 0.01
                    d = 14 + 40 * k
                    c = round(170 - 70 * k)
                    pygame.draw.circle(surface, (c, c - 8, c - 20),
                                       (x + round(math.cos(a) * d), y - 6 + round(math.sin(a) * d * 0.5)),
                                       max(1, round(6 * (1 - k))))
                if k < 0.5:
                    img = rock_img.copy()
                    img.set_alpha(round(255 * (1 - k * 2)))
                    surface.blit(img, img.get_rect(midbottom=(x, y + 10)))
                continue
            fall = warn - t
            if 0 <= fall < 0.45:                                    # cade negli ultimi istanti
                height = (fall / 0.45) ** 2 * 520
                surface.blit(rock_img, rock_img.get_rect(midbottom=(x, y + 10 - round(height))))

    def _do_windup(self, dt, player):
        self._timer -= dt
        if self._timer <= 0:
            if self._is_feint and not self._feint_done:
                self._phase = "feint_pause"
                self._timer = 0.38
            else:
                self._phase        = "charging"
                play("boss_charge", 0.9)
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
        self._move(intended, wall_rects, use_bodies=False)   # ti travolge: si ferma solo sui muri

        # Danno al player durante la carica — una sola volta per passata.
        # La carica NON si schiva con la capriola: bisogna togliersi dalla traiettoria.
        if not self._charge_hit and self.rect.colliderect(player.rect):
            if player.take_damage(int(s.BOSS_DAMAGE_CHARGE * self._dmg_mult), unblockable=True):
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
        play("boss_stun")
        self._timer = stun_t

    def _do_stunned(self, dt):
        self._timer -= dt
        if self._timer <= 0:
            self._phase           = "patrol"
            self._attack_timer    = 1.5
            self._charge_cd       = s.BOSS_CHARGE_RAGE_CD if self._rage else s.BOSS_CHARGE_CD
            self._proximity_timer = 0.0

    def _do_tail_spin(self, dt, player):
        self._timer -= dt
        if self._timer <= 0:
            dist = (player.pos - self.pos).length()
            if dist <= s.BOSS_TAIL_RANGE:
                if player.take_damage(int(s.BOSS_TAIL_DAMAGE * self._dmg_mult), attacker=self):
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
        d = self._direction_index()

        if self._phase == "tail_spin":                       # codata: gira su se stesso
            return anims["idle"][(d + ticks // 45) % 8][0]
        if self._phase == "charging":                        # carica: corsa veloce
            frames = anims["walk"][d]
            return frames[(ticks // 45) % len(frames)]
        attack = anims.get("attack", anims["idle"])[d]
        if self._phase == "knife_windup":                    # alza le braccia: i coltelli si sollevano
            frac = 1.0 - self._timer / self._knife_windup_total()
            return attack[min(s.ENEMY_ATTACK_STRIKE - 1, int(frac * s.ENEMY_ATTACK_STRIKE))]
        if self._phase == "windup":                          # si prepara alla carica
            return attack[1]
        if self._phase == "slam":                            # pestone: alza e abbatte la mazza
            frac = 1.0 - self._timer / s.BOSS_SLAM_TIME
            return attack[min(len(attack) - 1, int(frac * len(attack)))]
        if self._phase in ("stunned", "feint_pause"):
            return anims["idle"][d][0]
        return self._current_frame()                         # pattuglia: cammina / colpo base

    def draw(self, surface, camera_offset=(0, 0)):
        cx = round(self.pos.x) - camera_offset[0]
        cy = round(self.pos.y) - camera_offset[1]

        self._draw_knives(surface, cx, cy, behind=True)

        frame = self._boss_frame()
        if frame is not None:
            assets = AssetManager.get()
            base_frame = frame
            if self._phase == "stunned":
                frame = assets.tinted(frame, (120, 150, 255))
            elif self._rage:
                frame = assets.tinted(frame, (255, 120, 110))
            glow = self._windup_frac()
            if glow is not None:
                frame = warm_glow(frame, glow)
                outline, t = tell_outline(base_frame, glow, thick=4)
                surface.blit(outline, outline.get_rect(center=(cx, cy)))
            if self._hit_flash > 0:
                frame = frame.copy()
                frame.fill((150, 140, 120), special_flags=pygame.BLEND_RGB_ADD)
            surface.blit(frame, frame.get_rect(center=(cx, cy)))
        else:
            self._draw_procedural_body(surface, cx, cy)

        self._draw_knives(surface, cx, cy, behind=False)
        glow = self._windup_frac()
        if glow is not None:
            draw_glint(surface, cx + round(self._facing.x * 22), cy - 28 + round(self._facing.y * 8), glow, 1.4)
        self._draw_indicators(surface, cx, cy)

    def _windup_frac(self) -> "float | None":
        """Avanzamento (0→1) della carica di un attacco in corso, o None."""
        if self._phase == "windup":
            total = s.BOSS_WINDUP_RAGE_TIME if self._rage else s.BOSS_WINDUP_TIME
            return max(0.0, min(1.0, 1.0 - self._timer / total))
        if self._phase == "slam":
            return 1.0 - self._timer / s.BOSS_SLAM_TIME
        if self._phase == "knife_windup":
            return 1.0 - self._timer / self._knife_windup_total()
        if self._phase == "patrol" and self._windup > 0:
            return 1.0 - self._windup / self._windup_total
        return None

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

        # Carica in preparazione: raspa il terreno e solleva polvere (nessuna freccia)
        if self._phase == "windup":
            t    = pygame.time.get_ticks() / 1000.0
            back = -self._charge_dir
            for k in range(3):
                ph = (t * 3.2 + k / 3) % 1.0
                px = cx + round(back.x * (18 + 24 * ph) + (k - 1) * 9)
                py = cy + 22 + round(back.y * (18 + 24 * ph) - 7 * ph)
                c  = round(150 - 60 * ph)
                pygame.draw.circle(surface, (c, c - 10, c - 25), (px, py), round(3 + 5 * ph), 2)

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

