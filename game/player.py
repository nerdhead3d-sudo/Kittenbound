import math
import pygame
from game import settings as s
from game.asset_manager import AssetManager
from game.sound import play
from game.input import InputManager
from game import gfx


class Player(pygame.sprite.Sprite):
    """Gatto guerriero: WASD, melee (click-sx), schivata (Space), spell (F)."""

    def __init__(self, x: float, y: float):
        super().__init__()
        assets = AssetManager.get()
        self.image  = assets.player_sprite()
        self._anims = assets.player_animations()
        self._walk_time  = 0.0      # avanza solo mentre il player si muove
        self._moving     = False
        self._attack_anim = 0.0     # > 0: animazione graffio in corso (scende a 0)
        self._attack_crit = False   # graffio critico (perfect dodge) → artigli dorati
        # Effetti della schivata: salto, scia di "fantasmi", polvere, atterraggio
        self._ghosts: list = []     # [pos, frame, età]
        self._ghost_timer = 0.0
        self._dust: list = []       # [x, y, vx, vy, età, durata]
        self._land_timer = 0.0
        # Parata dei proiettili
        self._parry_timer = 0.0     # > 0: i proiettili vengono respinti
        self._parry_cd    = 0.0
        self._parry_anim  = 0.0
        self._sparks: list = []     # [x, y, vx, vy, età]
        # Scritte che salgono sopra il gatto ("PARATA!", "PERFETTO!")
        self.flash_timer = 0.0      # lampo a schermo (letto da main.py)
        self.counter_targets: list = []   # nemici da contrattaccare (parata perfetta)
        # Hitbox fissa: indipendente dalla dimensione dello sprite
        size       = s.PLAYER_RADIUS * 2 + 8
        self.rect  = pygame.Rect(0, 0, size, size)
        self.rect.center = (int(x), int(y))
        self.pos   = pygame.math.Vector2(x, y)

        self.hp_max     = s.PLAYER_HP_MAX
        self.hp         = float(self.hp_max)
        self.energy_max = s.PLAYER_ENERGY_MAX
        self.energy     = float(self.energy_max)
        self.xp         = 0
        self.level      = 1
        self.gold       = s.START_GOLD

        self.melee_damage_bonus = 0
        self.upgrades: dict[str, int] = {}     # acquisti per tipo di potenziamento (prezzi crescenti)
        self.potions     = s.POTION_START
        self._potion_cd  = 0.0
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
        self._attack_buffer = 0.0   # attacco premuto durante la schivata: parte appena possibile

        # Magie (game/spells.py): possedute e le 2 equipaggiate (tasti F e R)
        self.spells_owned = ["claw_leap"]
        self.spell_slots  = ["claw_leap", None]
        self.nine_lives_timer = 0.0
        self.dark_sight_timer = 0.0
        self.decoy   = None             # Ombra Felina attiva
        self.hiss_fx = None             # [direzione, età] dell'onda del Soffio

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
    def jump_height(self) -> float:
        """Altezza del salto della schivata (0 a terra): arco a parabola."""
        if self._dodge_timer <= 0:
            return 0.0
        u = 1.0 - self._dodge_timer / s.PLAYER_DODGE_DURATION
        return math.sin(math.pi * u) * s.PLAYER_DODGE_JUMP

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

    def take_damage(self, amount: int, unblockable: bool = False, attacker=None) -> bool:
        """Schivata: nessun danno per tutta la sua durata. Schivata perfetta (colpo che arriva
        nei primi istanti): in più rallenta il tempo e carica un colpo critico (danno x3).
        unblockable: la capriola non protegge (carica del boss), solo l'invulnerabilità post-colpo."""
        if unblockable:
            if self._invincible_timer > 0:
                return False
        elif attacker is not None and self.parrying:      # colpo melee parato
            perfect = self.perfect_parry
            to_a = attacker.pos - self.pos
            if to_a.length_squared() > 0:
                self.facing = to_a.normalize()
            self.on_parry(self.pos + self.facing * 26, perfect)
            if perfect:                                     # contrattacco automatico
                self.counter_targets.append(attacker)
                self._attack_anim = sum(s.PLAYER_ATTACK_FRAME_T)
                self._attack_crit = True
            return False
        elif self.invincible:
            if self._in_perfect_window and self._slow_timer <= 0:
                self._slow_timer      = 1.2
                self._crit_armed      = True
                self._attack_cooldown = 0.0
                self.flash_timer      = s.PERFECT_FLASH_TIME
                self.energy = min(float(self.energy_max), self.energy + s.PLAYER_ENERGY_DODGE_COST)
                play("perfect_dodge")
            return False
        if self.hp - amount <= 0 and self.nine_lives_timer > 0:   # Nove Vite: salvo a 1 HP
            self.nine_lives_timer  = 0.0
            self.hp                = 1.0
            self._invincible_timer = 1.0
            self.flash_timer       = s.PERFECT_FLASH_TIME
            play("nine_lives_save", 1.0)
            return True
        self.hp = max(0.0, self.hp - amount)
        self._invincible_timer = s.PLAYER_INVINCIBILITY_TIME
        if self.hp > 0:
            play("meow", 0.9)                              # miagolio di dolore
        return True

    def apply_stun(self, duration: float):
        if not self.invincible:
            self._stunned_timer    = duration
            self._invincible_timer = duration

    def heal(self, amount: int):
        self.hp = min(float(self.hp_max), self.hp + amount)

    # ── Parata ────────────────────────────────────────────────────────────────

    @property
    def parrying(self) -> bool:
        return self._parry_timer > 0

    @property
    def perfect_parry(self) -> bool:
        """Primi istanti della parata: contrattacco / proiettile respinto più forte."""
        return self._parry_timer > s.PARRY_WINDOW - s.PARRY_PERFECT

    def try_parry(self) -> bool:
        if (self._parry_cd > 0 or self.is_dodging or self.is_stunned or self.is_leaping
                or self.energy < s.PARRY_ENERGY):
            return False
        self.energy      -= s.PARRY_ENERGY
        self._parry_timer = s.PARRY_WINDOW
        self._parry_cd    = s.PARRY_COOLDOWN
        self._parry_anim  = s.PARRY_WINDOW + 0.08
        play("parry_swing", 0.6)
        return True

    def on_parry(self, at: pygame.math.Vector2, perfect: bool = False):
        """Colpo parato: scintille ed energia restituita (perfetta: lampo in più)."""
        self.energy = min(float(self.energy_max), self.energy + s.PARRY_REFUND)
        for i in range(10):
            v = pygame.math.Vector2(1, 0).rotate(i * 36 + (at.x % 17)) * (140 + 12 * (i % 3))
            self._sparks.append([at.x, at.y, v.x, v.y, 0.0])
        if perfect:
            self.flash_timer = s.PERFECT_FLASH_TIME
            play("perfect_dodge", 0.8)
        play("parry", 0.9)

    def drink_potion(self) -> bool:
        """Beve una pozione di vita (tasto Q). False se non ne hai, sei a vita piena o in cooldown."""
        if self.potions <= 0 or self._potion_cd > 0 or not self.alive or self.hp >= self.hp_max:
            return False
        self.potions   -= 1
        self._potion_cd = s.POTION_COOLDOWN
        self.heal(s.POTION_HEAL)
        play("potion", 0.9)
        return True

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
        play("leap", 0.8)
        return True

    def cancel_spell(self):
        """Interrompe la sequenza spell in corso (es. recall all'hub)."""
        if self._spell_phase != "ready":
            self._spell_cooldown = s.SPELL_SHOT_COOLDOWN
        self._spell_phase  = "ready"
        self._marked_enemy = None
        self._mark_timer   = 0.0
        self._leap_timer   = 0.0
        self._claw_pending = False

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
            play("level_up", 0.8)

    # ── Azioni di combattimento ────────────────────────────────────────────────

    @property
    def attack_buffered(self) -> bool:
        return self._attack_buffer > 0

    def try_attack(self) -> 'pygame.Rect | None':
        if self.is_dodging and self._crit_armed:
            # dopo una schivata perfetta il contrattacco interrompe subito la capriola
            self._dodge_timer      = 0.0
            self._land_timer       = s.PLAYER_LAND_TIME
            self._invincible_timer = max(self._invincible_timer, 0.15)
        if self.is_dodging and not self.is_stunned:
            self._attack_buffer = s.PLAYER_ATTACK_BUFFER   # parte appena finisce la schivata
            return None
        if (self._attack_cooldown > 0 or self.is_stunned
                or self.energy < s.PLAYER_ENERGY_MELEE_COST):
            return None
        self._attack_buffer   = 0.0
        self.energy          -= s.PLAYER_ENERGY_MELEE_COST
        self._attack_cooldown = s.PLAYER_MELEE_COOLDOWN
        self._attack_active   = s.PLAYER_MELEE_ACTIVE
        self._attack_anim     = sum(s.PLAYER_ATTACK_FRAME_T)
        self._attack_crit     = self._crit_armed
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
        self._ghost_timer    = 0.0
        self._spawn_dust(6, -self._dodge_dir)
        play("dodge", 0.6)
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
        vel = pygame.math.Vector2(0, 0)
        if not self.is_stunned and not self.is_leaping:
            vel = InputManager.get().move_vector()      # WASD/frecce o stick (lunghezza ≤ 1)

        if self.is_dodging:
            move = self._dodge_dir * s.PLAYER_DODGE_SPEED * dt
        elif self.is_leaping and self._marked_enemy and self._marked_enemy.alive:
            to_target = self._marked_enemy.pos - self.pos
            move = (to_target.normalize() * 700 * dt
                    if to_target.length_squared() > 0
                    else pygame.math.Vector2(0, 0))
        else:
            if vel.length_squared() > 0 and not self.is_stunned:
                self.facing = vel.normalize()
            move = vel * s.PLAYER_SPEED * dt             # stick inclinato poco = cammina piano

        self._moving = move.length_squared() > 0
        if self._moving:
            self._walk_time += dt

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
        self._attack_anim      = max(0.0, self._attack_anim - dt)
        self._potion_cd        = max(0.0, self._potion_cd - dt)
        self._attack_buffer    = max(0.0, self._attack_buffer - dt)
        self._dodge_cooldown   = max(0.0, self._dodge_cooldown - dt)
        if self._dodge_timer > 0:
            self._dodge_timer = max(0.0, self._dodge_timer - dt)
            if self._dodge_timer <= 0:                # atterraggio
                self._land_timer = s.PLAYER_LAND_TIME
                self._spawn_dust(8)
        self._land_timer = max(0.0, self._land_timer - dt)
        self._parry_timer = max(0.0, self._parry_timer - dt)
        self._parry_cd    = max(0.0, self._parry_cd - dt)
        self._parry_anim  = max(0.0, self._parry_anim - dt)
        self.flash_timer  = max(0.0, self.flash_timer - dt)
        for sp in self._sparks:
            sp[0] += sp[2] * dt
            sp[1] += sp[3] * dt
            sp[2] *= 0.86
            sp[3] *= 0.86
            sp[4] += dt
        self._sparks = [sp for sp in self._sparks if sp[4] < 0.3]
        self._update_dodge_fx(dt)

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

        self._draw_dodge_fx(surface, camera_offset)
        image = self._current_frame()
        jump  = self.jump_height
        if self.is_dodging or self._land_timer > 0:
            w, h = image.get_size()
            if self._land_timer > 0:                  # atterraggio: si schiaccia
                k = self._land_timer / s.PLAYER_LAND_TIME
                sx, sy = 1 + 0.16 * k, 1 - 0.16 * k
            else:                                     # in volo: allungato nel senso del salto
                k = jump / s.PLAYER_DODGE_JUMP
                sx, sy = 1 - 0.08 * k, 1 + 0.10 * k
            image = pygame.transform.smoothscale(image, (round(w * sx), round(h * sy)))
        rect = image.get_rect(midbottom=(cx, cy + 36 - round(jump)))
        if self.decoy is not None:                    # Ombra Felina: il gatto vero si nasconde
            image = image.copy()
            image.set_alpha(95)
        surface.blit(image, rect)

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

        # Parata: mezzaluna di energia davanti al gatto
        if self.parrying:
            self._draw_parry_arc(surface, cx, cy)
        self._draw_sparks(surface, camera_offset)

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

        # Graffio: tre artigli che tagliano davanti al gatto dal frame del colpo in poi
        if self._attack_anim > 0:
            total   = sum(s.PLAYER_ATTACK_FRAME_T)
            strike  = sum(s.PLAYER_ATTACK_FRAME_T[:s.PLAYER_ATTACK_STRIKE])
            elapsed = total - self._attack_anim
            if elapsed >= strike:
                self._draw_claw_marks(surface, cx, cy, (elapsed - strike) / (total - strike))

    # ── Effetti della parata ──────────────────────────────────────────────────

    def _draw_parry_arc(self, surface: pygame.Surface, cx: int, cy: int):
        frac  = 1.0 - self._parry_timer / s.PARRY_WINDOW
        r     = round(30 + 16 * frac)
        layer = gfx.Surface((r * 2 + 8, r * 2 + 8), pygame.SRCALPHA)
        base  = math.atan2(-self.facing.y, self.facing.x)       # pygame.draw.arc: y verso l'alto
        alpha = round(230 * (1 - frac * 0.6))
        rect  = layer.get_rect().inflate(-8, -8)
        for w, col in ((7, (60, 160, 255, alpha // 2)), (3, (200, 240, 255, alpha))):
            pygame.draw.arc(layer, col, rect, base - 1.2, base + 1.2, w)
        surface.blit(layer, layer.get_rect(center=(cx, cy - 6)))

    def _draw_sparks(self, surface, camera_offset):
        for x, y, vx, vy, age in self._sparks:
            k  = age / 0.3
            p0 = (round(x) - camera_offset[0], round(y) - camera_offset[1])
            p1 = (round(x - vx * 0.03) - camera_offset[0], round(y - vy * 0.03) - camera_offset[1])
            pygame.draw.line(surface, (round(255 - 80 * k), 240, 255), p0, p1, 2)

    # ── Effetti della schivata ────────────────────────────────────────────────

    def _spawn_dust(self, count: int, bias: pygame.math.Vector2 = None):
        for i in range(count):
            a = (i / count) * math.tau
            v = pygame.math.Vector2(math.cos(a), math.sin(a) * 0.5) * 60
            if bias is not None:
                v += bias * 50
            self._dust.append([self.pos.x, self.rect.bottom - 4, v.x, v.y, 0.0, 0.32])

    def _update_dodge_fx(self, dt: float):
        if self.is_dodging:                           # scia: un fantasma ogni 30 ms
            self._ghost_timer -= dt
            if self._ghost_timer <= 0:
                self._ghost_timer = 0.03
                frame = AssetManager.get().tinted(self._current_frame(), (120, 210, 255)).copy()
                self._ghosts.append([pygame.math.Vector2(self.pos), frame, 0.0, self.jump_height])
        for g in self._ghosts:
            g[2] += dt
        self._ghosts = [g for g in self._ghosts if g[2] < 0.2]
        for d in self._dust:
            d[0] += d[2] * dt
            d[1] += d[3] * dt
            d[2] *= 0.9
            d[3] *= 0.9
            d[4] += dt
        self._dust = [d for d in self._dust if d[4] < d[5]]

    def _draw_dodge_fx(self, surface: pygame.Surface, camera_offset: tuple):
        for x, y, _, _, age, life in self._dust:
            k = age / life
            r = round(3 + 5 * k)
            c = round(150 - 40 * k)
            pygame.draw.circle(surface, (c, c - 8, c - 18),
                               (round(x) - camera_offset[0], round(y) - camera_offset[1]), r, max(1, round(2 * (1 - k))))
        for pos, frame, age, jump in self._ghosts:
            frame.set_alpha(round(150 * (1 - age / 0.2)))
            rect = frame.get_rect(midbottom=(round(pos.x) - camera_offset[0],
                                             round(pos.y) - camera_offset[1] + 36 - round(jump)))
            surface.blit(frame, rect)

    # ── Animazione ────────────────────────────────────────────────────────────

    def _current_frame(self) -> pygame.Surface:
        if not self._anims:
            return self.image
        angle = math.degrees(math.atan2(self.facing.y, self.facing.x))
        d     = round(angle / 45) % 8

        if self._parry_anim > 0 and "attack" in self._anims:     # parata: zampata veloce
            frames = self._anims["attack"][d]
            frac   = 1.0 - self._parry_anim / (s.PARRY_WINDOW + 0.08)
            return frames[min(len(frames) - 1, 1 + int(frac * 4))]

        if self._attack_anim > 0 and "attack" in self._anims:
            elapsed = sum(s.PLAYER_ATTACK_FRAME_T) - self._attack_anim
            frames  = self._anims["attack"][d]
            idx     = 0
            for dur in s.PLAYER_ATTACK_FRAME_T[:-1]:
                if elapsed < dur:
                    break
                elapsed -= dur
                idx     += 1
            return frames[min(idx, len(frames) - 1)]

        if self._moving and "walk" in self._anims:
            frames = self._anims["walk"][d]
            return frames[int(self._walk_time * s.PLAYER_WALK_FPS) % len(frames)]

        return self._anims["idle"][d][0]

    def _draw_claw_marks(self, surface: pygame.Surface, cx: int, cy: int, progress: float):
        """progress 0→1: gli artigli si allungano in fretta, poi svaniscono."""
        reveal = min(1.0, progress * 2.5)
        alpha  = 1.0 - max(0.0, (progress - 0.35) / 0.65)
        if alpha <= 0:
            return

        if self._attack_crit:
            glow_c, core_c = (255, 185, 50), (255, 245, 205)
        else:
            glow_c, core_c = (150, 135, 255), (245, 240, 255)

        length, spacing, bow = 26, 9, 8
        pad   = length + spacing + bow + 8
        layer = gfx.Surface((pad * 2, pad * 2), pygame.SRCALPHA)
        fwd   = pygame.math.Vector2(self.facing)
        right = pygame.math.Vector2(-fwd.y, fwd.x)          # la zampa destra taglia da destra a sinistra
        mid   = pygame.math.Vector2(pad, pad)
        steps = 10

        for k in (-1, 0, 1):
            pts, widths = [], []
            for i in range(int(steps * reveal) + 1):
                t = i / steps
                p = (mid + right * (1 - 2 * t) * length
                     + fwd * (k * spacing + math.sin(math.pi * t) * bow)
                     - right * k * 3)                         # artigli leggermente sfalsati
                pts.append(p)
                widths.append(max(1, round(4 * math.sin(math.pi * t) + 1)))
            for (a, b), w in zip(zip(pts, pts[1:]), widths[1:]):
                pygame.draw.line(layer, (*glow_c, int(110 * alpha)), a, b, w + 3)
            for (a, b), w in zip(zip(pts, pts[1:]), widths[1:]):
                pygame.draw.line(layer, (*core_c, int(255 * alpha)), a, b, w)

        center = pygame.math.Vector2(cx, cy) + fwd * s.PLAYER_MELEE_RANGE * 0.6
        surface.blit(layer, (round(center.x) - pad, round(center.y) - pad))
