import math
import pygame
from game import settings as s
from game.asset_manager import AssetManager


class Player(pygame.sprite.Sprite):
    """Gatto guerriero: WASD, melee (click-sx), schivata (Space), spell (F)."""

    def __init__(self, x: float, y: float):
        super().__init__()
        self.image = AssetManager.get().player_sprite()
        self.rect  = self.image.get_rect(center=(int(x), int(y)))
        self.pos   = pygame.math.Vector2(x, y)

        self.hp_max     = s.PLAYER_HP_MAX
        self.hp         = float(self.hp_max)
        self.energy_max = s.PLAYER_ENERGY_MAX
        self.energy     = float(self.energy_max)
        self.xp         = 0
        self.level      = 1
        self.gold       = 0

        self.melee_damage_bonus = 0
        self.hp_regen_bonus     = 0.0
        self.energy_regen_bonus = 0.0

        self.facing = pygame.math.Vector2(1, 0)

        # Melee
        self._attack_cooldown = 0.0
        self._attack_active   = 0.0

        # Dodge
        self._dodge_timer    = 0.0
        self._dodge_cooldown = 0.0
        self._dodge_dir      = pygame.math.Vector2(0, 0)

        # Invincibilità passiva (anti-multihit)
        self._invincible_timer = 0.0

        # Bullet time (perfect dodge)
        self._slow_timer = 0.0
        self._crit_armed = False

        # Stun (codata del boss)
        self._stunned_timer = 0.0

        # Spell: skill shot + balzo artiglio
        self._spell_phase    = "ready"   # "ready" / "shot_fired" / "marked_ready" / "leaping"
        self._marked_enemy   = None
        self._mark_timer     = 0.0
        self._leap_timer     = 0.0
        self._claw_pending   = False     # segnale a main.py: applica danno artiglio
        self._spell_cooldown = 0.0       # CD dopo che la sequenza si chiude

    # ── Proprietà ─────────────────────────────────────────────────────────────

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def _in_perfect_window(self) -> bool:
        if self._dodge_timer <= 0:
            return False
        return (s.PLAYER_DODGE_DURATION - self._dodge_timer) <= s.PLAYER_DODGE_PERFECT

    @property
    def invincible(self) -> bool:
        return self._invincible_timer > 0 or self.is_dodging or self.is_leaping

    @property
    def is_dodging(self) -> bool:
        return self._dodge_timer > 0

    @property
    def is_leaping(self) -> bool:
        return self._spell_phase == "leaping"

    @property
    def is_stunned(self) -> bool:
        return self._stunned_timer > 0

    @property
    def hp_pct(self) -> float:
        return self.hp / self.hp_max

    @property
    def energy_pct(self) -> float:
        return self.energy / self.energy_max

    @property
    def xp_pct(self) -> float:
        thresholds = s.XP_PER_LEVEL
        if self.level >= len(thresholds):
            return 1.0
        prev = thresholds[self.level - 1] if self.level > 0 else 0
        nxt  = thresholds[self.level]
        span = nxt - prev
        return (self.xp - prev) / span if span > 0 else 1.0

    # ── Danni, cure, stun ─────────────────────────────────────────────────────

    def take_damage(self, amount: int) -> bool:
        if self.invincible:
            if self._in_perfect_window and self._slow_timer <= 0:
                self._slow_timer      = 1.2
                self._crit_armed      = True
                self._attack_cooldown = 0.0
            return False
        self.hp = max(0.0, self.hp - amount)
        self._invincible_timer = s.PLAYER_INVINCIBILITY_TIME
        return True

    def apply_stun(self, duration: float):
        if not self.invincible:
            self._stunned_timer    = duration
            self._invincible_timer = duration

    def heal(self, amount: int):
        self.hp = min(float(self.hp_max), self.hp + amount)

    def restore_energy(self, amount: int):
        self.energy = min(float(self.energy_max), self.energy + amount)

    # ── Spell ─────────────────────────────────────────────────────────────────

    def mark_enemy(self, enemy):
        """Chiamato da room quando lo spell shot colpisce un nemico."""
        self._marked_enemy = enemy
        self._mark_timer   = s.SPELL_MARK_DURATION
        self._spell_phase  = "marked_ready"

    def try_cast_spell(self) -> bool:
        if (self._spell_phase != "ready" or self.is_stunned
                or self._spell_cooldown > 0
                or self.energy < s.PLAYER_ENERGY_SPELL_COST):
            return False
        self.energy      -= s.PLAYER_ENERGY_SPELL_COST
        self._spell_phase = "shot_fired"
        self._mark_timer  = 2.0    # timeout se il proiettile non colpisce
        return True

    def try_leap(self) -> bool:
        if (self._spell_phase != "marked_ready" or
                self._marked_enemy is None or not self._marked_enemy.alive):
            return False
        self._spell_phase = "leaping"
        self._leap_timer  = 0.30
        return True

    # ── Esperienza e livelli ──────────────────────────────────────────────────

    def gain_xp(self, amount: int):
        self.xp += amount
        self._check_levelup()

    def _check_levelup(self):
        thresholds = s.XP_PER_LEVEL
        while self.level < len(thresholds) and self.xp >= thresholds[self.level]:
            self.level      += 1
            self.hp_max     += s.HP_BONUS_PER_LEVEL
            self.hp          = min(self.hp + s.HP_BONUS_PER_LEVEL, float(self.hp_max))
            self.energy_max += s.ENERGY_BONUS_PER_LEVEL

    # ── Azioni di combattimento ────────────────────────────────────────────────

    def try_attack(self) -> 'pygame.Rect | None':
        if (self._attack_cooldown > 0 or self.is_dodging or self.is_stunned
                or self.energy < s.PLAYER_ENERGY_MELEE_COST):
            return None
        self.energy          -= s.PLAYER_ENERGY_MELEE_COST
        self._attack_cooldown = s.PLAYER_MELEE_COOLDOWN
        self._attack_active   = s.PLAYER_MELEE_ACTIVE
        return self._melee_hitbox()

    def try_dodge(self, move_vec: pygame.math.Vector2) -> bool:
        if (self._dodge_cooldown > 0 or self.is_dodging or self.is_stunned
                or self.energy < s.PLAYER_ENERGY_DODGE_COST):
            return False
        self.energy         -= s.PLAYER_ENERGY_DODGE_COST
        direction            = move_vec if move_vec.length_squared() > 0 else self.facing
        self._dodge_dir      = direction.normalize()
        self._dodge_timer    = s.PLAYER_DODGE_DURATION
        self._dodge_cooldown = s.PLAYER_DODGE_COOLDOWN
        return True

    def _melee_hitbox(self) -> pygame.Rect:
        size = s.PLAYER_MELEE_RANGE
        cx   = self.pos.x + self.facing.x * size * 0.6
        cy   = self.pos.y + self.facing.y * size * 0.6
        return pygame.Rect(int(cx - size // 2), int(cy - size // 2), size, size)

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float, wall_rects: list | None = None):
        # ── Spell phase ─────────────────────────────────────────────────────
        if self._spell_phase == "shot_fired":
            self._mark_timer -= dt
            if self._mark_timer <= 0:
                self._spell_phase    = "ready"
                self._spell_cooldown = s.SPELL_SHOT_COOLDOWN

        elif self._spell_phase == "marked_ready":
            self._mark_timer -= dt
            if self._mark_timer <= 0 or (self._marked_enemy and not self._marked_enemy.alive):
                self._spell_phase    = "ready"
                self._marked_enemy   = None
                self._spell_cooldown = s.SPELL_SHOT_COOLDOWN

        elif self._spell_phase == "leaping":
            self._leap_timer -= dt
            if self._marked_enemy and self._marked_enemy.alive:
                dist_to = (self._marked_enemy.pos - self.pos).length()
                if dist_to <= 45 or self._leap_timer <= 0:
                    self._claw_pending = True
            else:
                self._spell_phase    = "ready"
                self._marked_enemy   = None
                self._leap_timer     = 0.0
                self._spell_cooldown = s.SPELL_SHOT_COOLDOWN

        self._spell_cooldown = max(0.0, self._spell_cooldown - dt)

        # ── Stun ────────────────────────────────────────────────────────────
        self._stunned_timer = max(0.0, self._stunned_timer - dt)

        # ── Movimento ───────────────────────────────────────────────────────
        keys = pygame.key.get_pressed()
        vel  = pygame.math.Vector2(0, 0)

        if not self.is_stunned and not self.is_leaping:
            if keys[pygame.K_w] or keys[pygame.K_UP]:    vel.y -= 1
            if keys[pygame.K_s] or keys[pygame.K_DOWN]:  vel.y += 1
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:  vel.x -= 1
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]: vel.x += 1

        if self.is_dodging:
            move = self._dodge_dir * s.PLAYER_DODGE_SPEED * dt
        elif self.is_leaping and self._marked_enemy and self._marked_enemy.alive:
            to_target = self._marked_enemy.pos - self.pos
            move = (to_target.normalize() * 700 * dt
                    if to_target.length_squared() > 0
                    else pygame.math.Vector2(0, 0))
        else:
            if vel.length_squared() > 0:
                vel.normalize_ip()
                if not self.is_stunned:
                    self.facing = pygame.math.Vector2(vel)
            move = vel * s.PLAYER_SPEED * dt

        self.pos.x += move.x
        self.rect.centerx = round(self.pos.x)
        if wall_rects:
            self._resolve_x(wall_rects)

        self.pos.y += move.y
        self.rect.centery = round(self.pos.y)
        if wall_rects:
            self._resolve_y(wall_rects)

        if not wall_rects:
            margin = s.PLAYER_RADIUS
            self.pos.x = max(margin, min(s.SCREEN_W - margin, self.pos.x))
            self.pos.y = max(margin, min(s.SCREEN_H - margin, self.pos.y))
            self.rect.center = (round(self.pos.x), round(self.pos.y))

        # ── Timers ──────────────────────────────────────────────────────────
        self._invincible_timer = max(0.0, self._invincible_timer - dt)
        self._attack_cooldown  = max(0.0, self._attack_cooldown - dt)
        self._attack_active    = max(0.0, self._attack_active - dt)
        self._dodge_cooldown   = max(0.0, self._dodge_cooldown - dt)
        if self._dodge_timer > 0:
            self._dodge_timer = max(0.0, self._dodge_timer - dt)

        # ── Rigenerazione ───────────────────────────────────────────────────
        self.energy = min(float(self.energy_max),
                          self.energy + (s.PLAYER_ENERGY_REGEN + self.energy_regen_bonus) * dt)
        self.hp     = min(float(self.hp_max),
                          self.hp + (s.PLAYER_HP_REGEN + self.hp_regen_bonus) * dt)

    # ── Collisioni ────────────────────────────────────────────────────────────

    def _resolve_x(self, wall_rects: list):
        for wall in wall_rects:
            if self.rect.colliderect(wall):
                if self.pos.x < wall.centerx:
                    self.rect.right = wall.left
                else:
                    self.rect.left  = wall.right
                self.pos.x = float(self.rect.centerx)

    def _resolve_y(self, wall_rects: list):
        for wall in wall_rects:
            if self.rect.colliderect(wall):
                if self.pos.y < wall.centery:
                    self.rect.bottom = wall.top
                else:
                    self.rect.top    = wall.bottom
                self.pos.y = float(self.rect.centery)

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        if (self._invincible_timer > 0 and not self.is_stunned
                and int(pygame.time.get_ticks() / 50) % 2 == 0):
            return

        cx = round(self.pos.x) - camera_offset[0]
        cy = round(self.pos.y) - camera_offset[1]

        surface.blit(self.image, (self.rect.x - camera_offset[0], self.rect.y - camera_offset[1]))

        # Stordimento: stelle rotanti
        if self.is_stunned:
            t = pygame.time.get_ticks() / 280.0
            for i in range(3):
                angle = t * 3.5 + i * (math.pi * 2 / 3)
                sx = cx + int(math.cos(angle) * 24)
                sy = cy + int(math.sin(angle) * 24) - 4
                pygame.draw.circle(surface, (240, 220, 60), (sx, sy), 4)
                pygame.draw.circle(surface, (255, 180, 20), (sx, sy), 2)
            return

        # Perfect dodge
        if self._in_perfect_window:
            pygame.draw.circle(surface, (80, 240, 200), (cx, cy), s.PLAYER_RADIUS + 8, 3)

        # Crit armato
        if self._crit_armed and self._slow_timer <= 0:
            t  = pygame.time.get_ticks() / 1000.0
            pr = s.PLAYER_RADIUS + 9 + int(3 * math.sin(t * 9.0))
            pygame.draw.circle(surface, (240, 195, 45), (cx, cy), pr, 2)

        # Balzo in corso
        if self.is_leaping:
            pygame.draw.circle(surface, (80, 240, 130), (cx, cy), s.PLAYER_RADIUS + 6, 3)

        # Slash melee
        if self._attack_active > 0:
            tip_x = cx + int(self.facing.x * s.PLAYER_MELEE_RANGE)
            tip_y = cy + int(self.facing.y * s.PLAYER_MELEE_RANGE)
            perp  = pygame.math.Vector2(-self.facing.y, self.facing.x)
            spread = 18
            pygame.draw.line(surface, (230, 220, 255), (cx, cy), (tip_x, tip_y), 3)
            for sign in (-1, 1):
                ex = cx + int(self.facing.x * s.PLAYER_MELEE_RANGE * 0.5 + perp.x * spread * sign)
                ey = cy + int(self.facing.y * s.PLAYER_MELEE_RANGE * 0.5 + perp.y * spread * sign)
                pygame.draw.line(surface, (160, 150, 210), (cx, cy), (ex, ey), 2)
