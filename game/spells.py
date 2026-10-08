"""Magie del gatto. Se ne possono equipaggiare 2 alla volta (tasti F e R, col controller
Y e LB); si comprano e si equipaggiano dal Mago nell'hub. Nessun cooldown: il limite è l'energia.

Ogni magia: nome, descrizione, costo in energia, prezzo in oro. L'effetto è in cast().
"""
import math
import random
from dataclasses import dataclass

import pygame

from game import settings as s
from game import gfx
from game.asset_manager import AssetManager
from game.projectile import Projectile
from game.sound import play


@dataclass(frozen=True)
class Spell:
    name: str
    desc: str
    cost: int        # energia
    price: int       # oro (0 = posseduta dall'inizio)
    color: tuple


SPELLS = {
    "claw_leap":     Spell("Balzo Artigliato", "Colpo che marca, poi salti sul nemico", s.PLAYER_ENERGY_SPELL_COST, 0, (255, 130, 200)),
    "spectral_claw": Spell("Graffio Spettrale", "3 lame d'energia che trapassano",     s.SPELL_BLADE_COST, s.SPELL_BLADE_PRICE, (150, 220, 255)),
    "hiss":          Spell("Soffio",            "Respinge nemici e proiettili davanti", s.SPELL_HISS_COST, s.SPELL_HISS_PRICE, (240, 200, 120)),
    "dark_sight":    Spell("Occhi nel Buio",    "Vedi tutta la stanza e i nemici",      s.SPELL_SIGHT_COST, s.SPELL_SIGHT_PRICE, (190, 255, 140)),
    "shadow_cat":    Spell("Ombra Felina",      "Un'ombra attira i nemici al posto tuo", s.SPELL_SHADOW_COST, s.SPELL_SHADOW_PRICE, (170, 120, 255)),
    "nine_lives":    Spell("Nove Vite",         "Il prossimo colpo mortale ti lascia a 1 HP", s.SPELL_LIVES_COST, s.SPELL_LIVES_PRICE, (255, 215, 90)),
}
ORDER = ["claw_leap", "spectral_claw", "hiss", "dark_sight", "shadow_cat", "nine_lives"]


# ── Lancio ────────────────────────────────────────────────────────────────────

def cast(game, spell_id: str, direction: pygame.math.Vector2) -> bool:
    """Lancia la magia (il Balzo Artigliato è gestito a parte da main). False se non si può."""
    p, room = game.player, game.dungeon.current_room
    spell = SPELLS[spell_id]
    if p.is_stunned or p.energy < spell.cost:
        play("error", 0.4)
        return False
    if spell_id == "nine_lives" and p.nine_lives_timer > 0:
        return False                                          # già attiva
    if spell_id == "shadow_cat" and p.decoy is not None and p.decoy.alive:
        return False
    p.energy -= spell.cost
    if direction.length_squared() > 0:
        p.facing = direction.normalize()
    d = pygame.math.Vector2(p.facing)

    if spell_id == "spectral_claw":
        dmg = s.SPELL_BLADE_DAMAGE + p.melee_damage_bonus
        for a in (-s.SPELL_BLADE_SPREAD, 0, s.SPELL_BLADE_SPREAD):
            proj = Projectile(p.pos.x, p.pos.y, d.rotate(a), damage=dmg, owner="player",
                              speed=s.SPELL_BLADE_SPEED, max_range=s.SPELL_BLADE_RANGE, style="blade")
            proj.piercing = True
            game.player_projectiles.add(proj)
        play("spell_blade", 0.8)

    elif spell_id == "hiss":
        _hiss(p, room, d)
        play("hiss", 0.9)

    elif spell_id == "dark_sight":
        p.dark_sight_timer = s.SPELL_SIGHT_TIME
        play("dark_sight", 0.8)

    elif spell_id == "shadow_cat":
        p.decoy = Decoy(p)
        play("shadow", 0.8)

    elif spell_id == "nine_lives":
        p.nine_lives_timer = s.SPELL_LIVES_TIME
        play("nine_lives", 0.8)
    return True


def _hiss(p, room, d):
    """Cono davanti al gatto: allontana i nemici (interrompe il colpo che caricano) e
    distrugge i proiettili nemici."""
    half = math.cos(math.radians(s.SPELL_HISS_ARC / 2))
    for e in list(room.enemies):
        to_e = e.pos - p.pos
        dist = to_e.length()
        if dist > s.SPELL_HISS_RANGE or (dist > 1 and to_e.normalize().dot(d) < half):
            continue
        push = to_e.normalize() if dist > 1 else pygame.math.Vector2(d)
        room.apply_single_damage(e, s.SPELL_HISS_DAMAGE, p)
        if getattr(e, "ENEMY_TYPE", "") == "boss" or not e.alive:
            continue                                          # il boss è troppo pesante
        for _ in range(8):                                    # spinta a passi: si ferma ai muri
            e._move(push * (s.SPELL_HISS_PUSH / 8), room._enemy_wall_rects, use_bodies=False)
        if getattr(e, "_windup", 0) > 0:                      # colpo interrotto
            e._windup = 0.0
            e._attack_timer = max(getattr(e, "_attack_timer", 0), 0.8)
    for proj in list(room.enemy_projectiles):
        to_p = proj.pos - p.pos
        if to_p.length() <= s.SPELL_HISS_RANGE and (to_p.length() < 1 or to_p.normalize().dot(d) >= half):
            proj.kill()
    p.hiss_fx = [pygame.math.Vector2(d), 0.0]


# ── Ombra Felina ──────────────────────────────────────────────────────────────

class Decoy:
    """Ombra del gatto: corre per la stanza e i nemici la scambiano per il gatto (la
    inseguono, la colpiscono, le sparano). Sparisce dopo un po' o dopo qualche colpo."""

    def __init__(self, player):
        self._p     = player
        self.pos    = pygame.math.Vector2(player.pos)
        self.rect   = player.rect.copy()
        self.facing = pygame.math.Vector2(player.facing)
        self.vel    = pygame.math.Vector2(player.facing) * s.SPELL_SHADOW_SPEED   # parte in avanti
        self.timer  = s.SPELL_SHADOW_TIME
        self.hits   = s.SPELL_SHADOW_HITS
        self._turn  = 0.6                         # tra quanto cambia direzione
        self._anim  = 0.0
        self.frame  = AssetManager.get().tinted(player._current_frame(), (175, 140, 255))

    @property
    def alive(self) -> bool:
        return self.timer > 0 and self.hits > 0

    def update(self, dt: float, walls=(), enemies=()):
        self.timer -= dt
        self._anim += dt
        self._turn -= dt
        if self._turn <= 0:                       # cambia strada: lontano dal nemico più vicino
            self._turn = random.uniform(0.5, 0.9)
            away = pygame.math.Vector2()
            near = min(enemies, key=lambda e: (e.pos - self.pos).length_squared(), default=None)
            if near is not None and (self.pos - near.pos).length_squared() > 0:
                away = (self.pos - near.pos).normalize()
            far = near is None or (self.pos - near.pos).length() > 140
            # gira per la stanza: si allontana solo se un nemico le è addosso
            d = (self.vel.normalize() + (away * 0.0 if far else away * 0.7)).rotate(random.uniform(-70, 70))
            if d.length_squared() > 0:
                self.vel = d.normalize() * s.SPELL_SHADOW_SPEED
        for axis in (0, 1):                       # movimento con i muri, come il gatto
            step = pygame.math.Vector2(self.vel.x * dt, 0) if axis == 0 else pygame.math.Vector2(0, self.vel.y * dt)
            self.pos += step
            self.rect.center = (round(self.pos.x), round(self.pos.y))
            if any(self.rect.colliderect(w) for w in walls):
                self.pos -= step
                self.rect.center = (round(self.pos.x), round(self.pos.y))
                if axis == 0:
                    self.vel.x = -self.vel.x      # rimbalza sul muro
                else:
                    self.vel.y = -self.vel.y
        if self.vel.length_squared() > 0:
            self.facing = self.vel.normalize()
        anims = AssetManager.get().player_animations()
        if anims and "walk" in anims:             # corre: fotogrammi della camminata del gatto
            ang    = math.degrees(math.atan2(self.facing.y, self.facing.x)) % 360
            frames = anims["walk"][round(ang / 45) % 8]
            frame  = frames[int(self._anim * 14) % len(frames)]
            self.frame = AssetManager.get().tinted(frame, (175, 140, 255))

    def take_damage(self, amount, unblockable=False, attacker=None) -> bool:
        self.hits -= 1
        play("shadow", 0.5)
        return True

    def apply_stun(self, duration):
        pass

    # tutto il resto (parata, schivata, ...) come il gatto vero
    def __getattr__(self, name):
        return getattr(self._p, name)

    def draw(self, surface, cam):
        t   = pygame.time.get_ticks() / 1000.0
        img = self.frame.copy()
        img.set_alpha(round(120 + 50 * math.sin(t * 9)) if self.timer < 1.0 else 170)
        cx, cy = round(self.pos.x) - cam[0], round(self.pos.y) - cam[1]
        surface.blit(img, img.get_rect(midbottom=(cx, cy + 36)))
        for k in range(4):                                    # fumo viola che sale
            ph = (t * 0.8 + k / 4) % 1.0
            pygame.draw.circle(surface, (120, 80, 190), (cx + round(math.sin(t * 2 + k * 1.6) * 14),
                                                          cy + 10 - round(ph * 40)), max(1, round(4 * (1 - ph))))


# ── Effetti sul gatto ─────────────────────────────────────────────────────────

def update_player(p, dt: float, walls=(), enemies=()):
    p.nine_lives_timer = max(0.0, p.nine_lives_timer - dt)
    p.dark_sight_timer = max(0.0, p.dark_sight_timer - dt)
    if p.decoy is not None:
        p.decoy.update(dt, walls, enemies)
        if not p.decoy.alive:
            p.decoy = None
    if p.hiss_fx is not None:
        p.hiss_fx[1] += dt
        if p.hiss_fx[1] > 0.3:
            p.hiss_fx = None


def draw_player_fx(surface, p, cam):
    """Aura di Nove Vite e onda del Soffio (sopra la stanza, sotto l'HUD)."""
    cx, cy = round(p.pos.x) - cam[0], round(p.pos.y) - cam[1]
    t = pygame.time.get_ticks() / 1000.0
    if p.nine_lives_timer > 0:                                # nove scintille dorate in orbita
        fade = min(1.0, p.nine_lives_timer / 1.0)
        for k in range(9):
            a = t * 2.2 + k * math.tau / 9
            x, y = cx + round(math.cos(a) * 26), cy - 6 + round(math.sin(a) * 12)
            pygame.draw.circle(surface, (255, 215, 90), (x, y), 3 if fade > 0.5 or int(t * 10) % 2 else 2)
            pygame.draw.circle(surface, (255, 250, 210), (x, y), 1)
    if p.hiss_fx is not None:                                 # onde ad arco che si allargano
        d, age = p.hiss_fx
        k = age / 0.3
        base = math.atan2(-d.y, d.x)
        half = math.radians(s.SPELL_HISS_ARC / 2)
        for i in range(3):
            r = round(30 + (s.SPELL_HISS_RANGE - 30) * min(1.0, k + i * 0.12))
            col = (round(240 * (1 - k)), round(210 * (1 - k)), round(150 * (1 - k)))
            pygame.draw.arc(surface, col, (cx - r, cy - r, r * 2, r * 2), base - half, base + half, 3)


def draw_blade(surface, proj, cam):
    """Lama spettrale: mezzaluna azzurra con scia."""
    cx, cy = round(proj.pos.x) - cam[0], round(proj.pos.y) - cam[1]
    d = proj.vel.normalize() if proj.vel.length_squared() > 0 else pygame.math.Vector2(1, 0)
    n = pygame.math.Vector2(-d.y, d.x)
    for k, (w, col) in enumerate(((3, (90, 160, 230)), (2, (180, 230, 255)))):
        back = 6 * k
        pts = [(cx + n.x * 13 - d.x * (4 + back), cy + n.y * 13 - d.y * (4 + back)),
               (cx + d.x * 7, cy + d.y * 7),
               (cx - n.x * 13 - d.x * (4 + back), cy - n.y * 13 - d.y * (4 + back))]
        pygame.draw.lines(surface, col, False, pts, w + 1)
    pygame.draw.circle(surface, (235, 250, 255), (cx + round(d.x * 5), cy + round(d.y * 5)), 2)
