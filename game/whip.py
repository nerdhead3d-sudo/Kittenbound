"""Frusta a 5 punte del Topo Armaturato, simulata come corde (Verlet) in 3D finto:
x/y sul pavimento, z = altezza. Il manico segue la mano del boss; le code hanno peso
e inerzia, quindi pendono a terra, si trascinano quando cammina e si piegano nello
schiocco, con le punte che accelerano come in una frustata vera.

Aspetto ripreso dal modello "frusta5 punte.glb": manico con anello, cinque code di
cuoio scuro, punte a pugnale argentate.
"""
import math
import pygame

TAILS        = 5
SEGMENTS     = 7
STIFFNESS    = 0.45       # resistenza a piegarsi: archi morbidi invece di zig-zag
FAN          = 2.2        # apertura a ventaglio delle code (px per segmento)
GRAVITY      = 2300.0     # px/s² verso il pavimento (z)
DAMPING      = 0.985      # attrito dell'aria
FLOOR_FRICT  = 0.55       # le code che strisciano a terra rallentano
SUBSTEPS     = 3
ITERATIONS   = 5
HANDLE_LEN   = 22
Z_SCREEN     = 0.85       # quanto l'altezza sposta verso l'alto sullo schermo (camera 3/4)
FLOOR_OFFSET = 26         # z=0 corrisponde ai piedi del boss, non al centro dello sprite

C_LEATHER    = (62, 40, 30)
C_LEATHER_LT = (138, 100, 72)
C_HANDLE     = (68, 44, 30)
C_BLADE      = (196, 200, 210)
C_BLADE_DK   = (64, 64, 74)


class Whip:
    def __init__(self, length: float):
        self.length = length
        # code leggermente diverse in lunghezza: si aprono a ventaglio da sole
        self._seg = [length * (0.9 + 0.05 * abs(i - TAILS // 2)) / SEGMENTS for i in range(TAILS)]
        self.hand    = pygame.math.Vector3(0, 0, 30)
        self.tip     = pygame.math.Vector3(0, 0, 30)          # fine del manico (attacco delle code)
        self._pts    = None
        self._prev   = None
        self._trails = [[] for _ in range(TAILS)]             # ultime posizioni delle punte
        self._crack  = None                                   # (pos, età) lampo dello schiocco

    # ── Simulazione ───────────────────────────────────────────────────────────

    def _place(self, base: pygame.math.Vector3, direction: pygame.math.Vector2):
        d = pygame.math.Vector3(direction.x, direction.y, 0)
        self._pts = [[base + d * self._seg[t] * j for j in range(SEGMENTS + 1)] for t in range(TAILS)]
        for tail in self._pts:
            for p in tail:
                p.z = max(0.0, p.z - 20)
        self._prev = [[pygame.math.Vector3(p) for p in tail] for tail in self._pts]

    def update(self, dt: float, hand: pygame.math.Vector3, handle_dir: pygame.math.Vector2,
               swinging: bool = False):
        """hand: mano del boss (x, y, altezza); handle_dir: dove punta il manico."""
        hd = handle_dir.normalize() if handle_dir.length_squared() > 0 else pygame.math.Vector2(1, 0)
        self.hand = pygame.math.Vector3(hand)
        self.tip  = self.hand + pygame.math.Vector3(hd.x, hd.y, 0.25) * HANDLE_LEN
        if self._pts is None:
            self._place(self.tip, hd)
        side = pygame.math.Vector3(-hd.y, hd.x, 0)

        h = dt / SUBSTEPS
        for _ in range(SUBSTEPS):
            for t, (tail, prev) in enumerate(zip(self._pts, self._prev)):
                tail[0] = self.tip + side * ((t - TAILS // 2) * 2.5)
                prev[0] = pygame.math.Vector3(tail[0])
                for j in range(1, SEGMENTS + 1):
                    p, q = tail[j], prev[j]
                    vel = (p - q) * DAMPING
                    if p.z <= 0.5:                            # striscia sul pavimento
                        vel.x *= FLOOR_FRICT
                        vel.y *= FLOOR_FRICT
                    q.update(p)
                    p += vel
                    p.z -= GRAVITY * h * h
                lateral = (t - TAILS // 2)
                for j in range(2, SEGMENTS + 1):             # ventaglio: le code si separano
                    off = (tail[j] - tail[0]).dot(side)
                    tail[j] += side * ((lateral * FAN * j - off) * 0.04)
                for _ in range(ITERATIONS):
                    seg = self._seg[t]
                    for j in range(SEGMENTS):                 # lunghezza dei segmenti costante
                        a, b = tail[j], tail[j + 1]
                        delta = b - a
                        dist = delta.length() or 1e-6
                        corr = delta * ((dist - seg) / dist)
                        if j == 0:
                            b -= corr
                        else:
                            a += corr * 0.5
                            b -= corr * 0.5
                    for j in range(SEGMENTS - 1):             # rigidità: il cuoio non si spezza
                        a, c = tail[j], tail[j + 2]
                        delta = c - a
                        dist = delta.length() or 1e-6
                        rest = seg * 1.9
                        if dist < rest:
                            corr = delta * ((dist - rest) / dist) * STIFFNESS
                            if j == 0:
                                c -= corr
                            else:
                                a += corr * 0.5
                                c -= corr * 0.5
                    for p in tail[1:]:
                        if p.z < 0:
                            p.z = 0.0

        for t, tail in enumerate(self._pts):                   # scia delle punte
            trail = self._trails[t]
            trail.append(pygame.math.Vector3(tail[-1]))
            del trail[:-6 if swinging else -1]
        if self._crack:
            self._crack = (self._crack[0], self._crack[1] + dt)
            if self._crack[1] > 0.14:
                self._crack = None

    def crack(self):
        """Fine dello schiocco: lampo sulla punta più veloce."""
        if not self._pts:
            return
        speeds = [(tail[-1] - prev[-1]).length() for tail, prev in zip(self._pts, self._prev)]
        fastest = self._pts[speeds.index(max(speeds))]
        self._crack = (pygame.math.Vector3(fastest[-1]), 0.0)

    def hits(self, pos: pygame.math.Vector2, radius: float) -> bool:
        """True se la parte esterna di una coda passa entro radius dal punto (sul pavimento)."""
        if not self._pts:
            return False
        r2 = radius * radius
        for tail in self._pts:
            for p in tail[SEGMENTS // 3:]:
                if (p.x - pos.x) ** 2 + (p.y - pos.y) ** 2 <= r2 and p.z < 60:
                    return True
        return False

    # ── Disegno ───────────────────────────────────────────────────────────────

    @staticmethod
    def _scr(p, cam):
        return (round(p.x - cam[0]), round(p.y - cam[1] + FLOOR_OFFSET - p.z * Z_SCREEN))

    def draw(self, surface: pygame.Surface, cam: tuple, layer: str, pivot_y: float, swinging: bool):
        """layer "back": code dietro al boss (y < pivot_y); "front": quelle davanti + manico."""
        if not self._pts:
            return
        front = layer == "front"
        for t, tail in enumerate(self._pts):
            mid_y = tail[SEGMENTS // 2].y
            if (mid_y >= pivot_y) != front:
                continue
            # ombra a terra (solo dove la coda è sollevata)
            for j in range(SEGMENTS):
                a, b = tail[j], tail[j + 1]
                if a.z > 3:
                    pygame.draw.line(surface, (30, 26, 24),
                                     (round(a.x - cam[0]), round(a.y - cam[1] + FLOOR_OFFSET)),
                                     (round(b.x - cam[0]), round(b.y - cam[1] + FLOOR_OFFSET)), 2)
            if swinging:                                       # scia argentata della punta
                trail = self._trails[t]
                for k in range(1, len(trail)):
                    shade = 120 + 22 * k
                    pygame.draw.line(surface, (shade, shade, min(255, shade + 20)),
                                     self._scr(trail[k - 1], cam), self._scr(trail[k], cam), max(1, k // 2))
            # coda di cuoio, più spessa vicino al manico
            pts = [self._scr(p, cam) for p in tail]
            for j in range(SEGMENTS):
                w = 3 if j < SEGMENTS // 2 else 2
                pygame.draw.line(surface, C_LEATHER, pts[j], pts[j + 1], w)
            pygame.draw.aalines(surface, C_LEATHER_LT, False, pts[:SEGMENTS - 1])
            self._draw_blade(surface, tail[-2], tail[-1], cam)

        if front:                                              # manico con anello
            h0, h1 = self._scr(self.hand, cam), self._scr(self.tip, cam)
            pygame.draw.line(surface, (30, 20, 14), h0, h1, 8)
            pygame.draw.line(surface, C_HANDLE, h0, h1, 6)
            pygame.draw.line(surface, (120, 86, 56), h0, h1, 1)
            ring = (h0[0] - round((h1[0] - h0[0]) * 0.25), h0[1] - round((h1[1] - h0[1]) * 0.25))
            pygame.draw.circle(surface, (150, 150, 160), ring, 4, 2)
            if self._crack:
                p, age = self._crack
                k = 1 - age / 0.14
                c = self._scr(p, cam)
                pygame.draw.circle(surface, (255, 250, 230), c, round(3 + 9 * (1 - k)), 2)
                for a in range(4):
                    ang = a * math.pi / 2 + 0.6
                    e = (c[0] + round(math.cos(ang) * 14 * k), c[1] + round(math.sin(ang) * 14 * k))
                    pygame.draw.line(surface, (255, 245, 200), c, e, 2)

    def _draw_blade(self, surface, prev, tip, cam):
        a, b = self._scr(prev, cam), self._scr(tip, cam)
        d = pygame.math.Vector2(b[0] - a[0], b[1] - a[1])
        if d.length_squared() < 1e-6:
            d = pygame.math.Vector2(1, 0)
        d = d.normalize()
        n = pygame.math.Vector2(-d.y, d.x)
        tipv = pygame.math.Vector2(b)
        poly = [tipv + d * 9, tipv + n * 3.5, tipv - d * 4, tipv - n * 3.5]
        pygame.draw.polygon(surface, C_BLADE, poly)
        pygame.draw.polygon(surface, C_BLADE_DK, poly, 1)
        pygame.draw.line(surface, (240, 242, 248), tipv, tipv + d * 7)
